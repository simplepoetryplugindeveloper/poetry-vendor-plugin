"""Commands for the Poetry Vendor Plugin."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from cleo.helpers import option
from poetry.console.commands.command import Command
from poetry.core.constraints.version.parser import parse_constraint
from poetry.core.constraints.version.version import Version


_LOCK_VERSION = 1
_LOCK_FILENAME = "vendor.lock"


def _normalize_package_name(name: str) -> str:
    """Normalize a package name for use in a wheel filename.

    Wheel distribution names use underscores and are lower-cased.
    """
    return re.sub(r"[-_.]+", "_", name).lower()


def _lock_file_path(vendor_dir: Path) -> Path:
    """Return the path to the vendor lock file."""
    return vendor_dir / _LOCK_FILENAME


def _read_lock(vendor_dir: Path) -> dict[str, Any]:
    """Read the vendor lock file, returning a fresh structure if missing."""
    lock_path = _lock_file_path(vendor_dir)
    if not lock_path.exists():
        return {"version": _LOCK_VERSION, "packages": {}}

    try:
        with lock_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": _LOCK_VERSION, "packages": {}}

    if not isinstance(data, dict):
        return {"version": _LOCK_VERSION, "packages": {}}

    data.setdefault("version", _LOCK_VERSION)
    data.setdefault("packages", {})
    return data


def _write_lock(vendor_dir: Path, lock: dict[str, Any]) -> None:
    """Write the vendor lock file."""
    lock_path = _lock_file_path(vendor_dir)
    with lock_path.open("w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2)
        f.write("\n")


def _parse_wheel_filename(filename: str) -> tuple[str, str]:
    """Return (normalized_package_name, version) from a wheel filename.

    Wheel filenames follow the format:
        {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    The version is always the second hyphen-separated segment.
    """
    if not filename.endswith(".whl"):
        raise ValueError(f"Not a wheel filename: {filename}")

    parts = filename[:-4].split("-")
    if len(parts) < 5:
        raise ValueError(f"Invalid wheel filename: {filename}")

    name = _normalize_package_name(parts[0])
    version = parts[1]
    return name, version


def _target_wheel_path(vendor_dir: Path, name: str) -> Path:
    """Return the stable, version-less path for a vendored wheel."""
    return vendor_dir / f"{_normalize_package_name(name)}.whl"


def _pip_requirement(name: str, version: str) -> str:
    """Convert a Poetry version specifier into a pip-compatible requirement.

    Poetry supports caret (^), tilde (~), and other shorthand specifiers that
    pip does not understand. We use Poetry's own parser to expand them to PEP 440
    and fall back to the raw package name for the wildcard version.
    """
    if version in ("*", ""):
        return name

    constraint = parse_constraint(version)
    constraint_str = str(constraint)

    if constraint_str == "*":
        return name

    if isinstance(constraint, Version):
        return f"{name}=={constraint_str}"

    return f"{name}{constraint_str}"


class VendorPullCommand(Command):
    """Download vendor packages from internal repositories to vendor/."""

    name = "vendor pull"
    description = "Download vendor packages from internal repositories to vendor/"

    options = [
        option("force", "f", "Force re-download even if package exists."),
        option("dry-run", None, "Show what would be downloaded without downloading."),
    ]

    def handle(self) -> int:
        poetry = self.poetry
        vendor_config = self._get_vendor_config(poetry)

        if vendor_config is None:
            return 1

        if not vendor_config:
            self.line_error(
                "<error>No [tool.vendor] configuration found in pyproject.toml</error>"
            )
            return 1

        vendor_dir = Path(vendor_config.get("vendor-dir", "vendor"))
        vendor_dir.mkdir(exist_ok=True)

        try:
            packages = self._expand_packages(vendor_config)
        except ValueError as e:
            self.line_error(f"<error>{e}</error>")
            return 1

        if not packages:
            self.line("<comment>No vendor packages configured.</comment>")
            return 0

        lock = _read_lock(vendor_dir)
        lock["packages"] = dict(lock.get("packages", {}))

        self.line(f"<info>Vendor directory: {vendor_dir.resolve()}</info>")
        self.line("")

        success_count = 0
        fail_count = 0

        for pkg in packages:
            name = pkg.get("name")
            source = pkg.get("source")
            version = pkg.get("version", "*")

            if not name or not source:
                self.line_error(
                    "<error>  ✗ Invalid config: missing name or source</error>"
                )
                fail_count += 1
                continue

            normalized_name = _normalize_package_name(name)
            target_path = _target_wheel_path(vendor_dir, name)
            locked_pkg = lock["packages"].get(name)

            self.line(f"<info>Processing {name}@{version}...</info>")

            if self.option("dry-run"):
                self.line(
                    f"  <comment>→ Would download from {source} and save as {target_path.name}</comment>"
                )
                success_count += 1
                continue

            # Check if already vendored and not forced
            if target_path.exists() and locked_pkg and not self.option("force"):
                self.line(
                    f"  <info>✓ Already vendored: {name}=={locked_pkg['version']}</info>"
                )
                success_count += 1
                continue

            # Remove existing target wheel and any stale wheels for this package
            if target_path.exists():
                target_path.unlink()
                self.line(f"  <comment>→ Removed old: {target_path.name}</comment>")

            for stale in vendor_dir.glob(f"{normalized_name}*.whl"):
                if stale.resolve() != target_path.resolve():
                    stale.unlink()
                    self.line(f"  <comment>→ Removed stale: {stale.name}</comment>")

            # Download using pip into a temporary directory inside vendor/
            try:
                with tempfile.TemporaryDirectory(dir=str(vendor_dir)) as tmp:
                    cmd = [
                        sys.executable,
                        "-m",
                        "pip",
                        "download",
                        "--no-deps",
                        "--only-binary",
                        ":all:",
                        "--index-url",
                        source,
                        "--dest",
                        tmp,
                        _pip_requirement(name, version),
                    ]

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True,
                    )

                    downloaded = list(Path(tmp).glob("*.whl"))
                    if not downloaded:
                        self.line_error(
                            "<error>  ✗ Download failed - no wheel found</error>"
                        )
                        fail_count += 1
                        continue

                    wheel = downloaded[0]
                    parsed_name, parsed_version = _parse_wheel_filename(wheel.name)
                    wheel.rename(target_path)

                    lock["packages"][name] = {
                        "version": parsed_version,
                        "filename": target_path.name,
                        "source": source,
                        "requested": version,
                    }

                    self.line(
                        f"  <info>✓ Downloaded: {name}=={parsed_version} -> {target_path.name}</info>"
                    )
                    success_count += 1

            except subprocess.CalledProcessError as e:
                self.line_error(f"<error>  ✗ Download failed: {e.stderr}</error>")
                fail_count += 1
            except Exception as e:
                self.line_error(f"<error>  ✗ Error: {e}</error>")
                fail_count += 1

        if not self.option("dry-run"):
            _write_lock(vendor_dir, lock)

        self.line("")
        self.line(
            f"<info>Done: {success_count} succeeded, {fail_count} failed</info>"
        )

        if success_count > 0 and not self.option("dry-run"):
            self.line("")
            self.line(
                "<comment>Remember to update your pyproject.toml dependencies to use path references:</comment>"
            )
            self.line(
                '  <comment>my-package = { path = "vendor/my_package.whl" }</comment>'
            )

        return 0 if fail_count == 0 else 1

    def _get_vendor_config(self, poetry: Any) -> dict[str, Any] | None:
        """Read vendor configuration from pyproject.toml."""
        pyproject = poetry.file.read()
        tool = pyproject.get("tool", {})

        if "poetry-vendor" in tool:
            self.line_error(
                "<error>Detected deprecated [tool.poetry-vendor] configuration.</error>"
            )
            self.line_error("Please migrate to the new [tool.vendor] format:")
            self.line_error("")
            self.line_error("  [tool.vendor]")
            self.line_error('  vendor-dir = "vendor"')
            self.line_error("")
            self.line_error("  [tool.vendor.server]")
            self.line_error('  server1 = "https://internal-pypi.example.com/simple/"')
            self.line_error("")
            self.line_error("  [tool.vendor.packages.server1]")
            self.line_error('  my-package = "^1.0.0"')
            self.line_error("")
            return None

        return tool.get("vendor", {})

    def _expand_packages(self, vendor_config: dict[str, Any]) -> list[dict[str, Any]]:
        """Expand [tool.vendor.server] and [tool.vendor.packages.*] into a package list."""
        servers = vendor_config.get("server", {})
        packages_by_server = vendor_config.get("packages", {})
        expanded: list[dict[str, Any]] = []

        if not isinstance(servers, dict):
            raise ValueError("[tool.vendor.server] must be a table of server URLs")

        if not isinstance(packages_by_server, dict):
            raise ValueError(
                "[tool.vendor.packages] must be a table of per-server package tables"
            )

        for server_name, server_packages in packages_by_server.items():
            source = servers.get(server_name)
            if source is None:
                raise ValueError(
                    f"Unknown server '{server_name}' referenced in "
                    f"[tool.vendor.packages.{server_name}]"
                )

            if not isinstance(server_packages, dict):
                raise ValueError(
                    f"[tool.vendor.packages.{server_name}] must be a table mapping "
                    "package names to version specifiers"
                )

            for pkg_name, version in server_packages.items():
                expanded.append(
                    {
                        "name": pkg_name,
                        "source": source,
                        "version": str(version),
                    }
                )

        return expanded


class VendorUpdateCommand(Command):
    """Update vendor packages to latest versions."""

    name = "vendor update"
    description = "Update vendor packages to their latest allowed versions"

    options = [
        option("package", "p", "Specific package to update", flag=False),
    ]

    def handle(self) -> int:
        package = self.option("package")
        if package:
            self.line(f"<info>Updating specific package: {package}</info>")
        return self.call("vendor pull", "--force")


class VendorListCommand(Command):
    """List vendored packages."""

    name = "vendor list"
    description = "List all vendored packages in the vendor directory"

    def handle(self) -> int:
        poetry = self.poetry
        vendor_config = self._get_vendor_config(poetry)

        if vendor_config is None:
            return 1

        vendor_dir = Path(vendor_config.get("vendor-dir", "vendor"))

        if not vendor_dir.exists():
            self.line(
                "<comment>Vendor directory does not exist. Run 'poetry vendor pull' first.</comment>"
            )
            return 0

        lock = _read_lock(vendor_dir)
        locked_packages = lock.get("packages", {})

        if locked_packages:
            self.line("<info>Vendored packages:</info>")
            for name, info in sorted(locked_packages.items()):
                filename = info.get("filename")
                version = info.get("version", "unknown")
                wheel_path = (
                    vendor_dir / filename
                    if filename
                    else _target_wheel_path(vendor_dir, name)
                )

                if wheel_path.exists():
                    size = wheel_path.stat().st_size
                    if size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f} KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                else:
                    size_str = "missing"

                self.line(
                    f"  <info>•</info> {name}=={version} ({filename}) <comment>({size_str})</comment>"
                )
            return 0

        # Fallback for vendor directories without a lock file
        wheels = list(vendor_dir.glob("*.whl"))
        if not wheels:
            self.line("<comment>No vendored packages found.</comment>")
            return 0

        self.line("<info>Vendored packages:</info>")
        for wheel in sorted(wheels):
            size = wheel.stat().st_size
            if size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"
            self.line(f"  <info>•</info> {wheel.name} <comment>({size_str})</comment>")

        return 0

    def _get_vendor_config(self, poetry: Any) -> dict[str, Any] | None:
        """Read vendor configuration from pyproject.toml."""
        pyproject = poetry.file.read()
        tool = pyproject.get("tool", {})

        if "poetry-vendor" in tool:
            self.line_error(
                "<error>Detected deprecated [tool.poetry-vendor] configuration.</error>"
            )
            self.line_error("Please migrate to the new [tool.vendor] format.")
            return None

        return tool.get("vendor", {})
