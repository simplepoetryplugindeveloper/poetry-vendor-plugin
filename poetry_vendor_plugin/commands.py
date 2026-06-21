"""Commands for the Poetry Vendor Plugin."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cleo.helpers import argument, option
from poetry.console.commands.command import Command
from poetry.core.constraints.version.parser import parse_constraint
from poetry.core.constraints.version.version import Version
from tomlkit import dumps as dumps_toml
from tomlkit import inline_table
from tomlkit import parse as parse_toml


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


def _dependency_name_key(name: str) -> str:
    """Return a canonical key for comparing dependency/package names."""
    return re.sub(r"[-_.]+", "", name).lower()


def _host_from_url(url: str) -> str:
    """Return the host (with port) from a URL."""
    return urlparse(url).netloc or url


def _pip_trusted_host_args(source: str, trusted_hosts: list[str]) -> list[str]:
    """Return --trusted-host args for pip when the source host is listed."""
    host = _host_from_url(source)
    if host in trusted_hosts:
        return ["--trusted-host", host]
    return []


def _find_dependency_key(dependencies: Any, name: str) -> str | None:
    """Find the pyproject.toml dependency key matching a package name."""
    target = _dependency_name_key(name)
    for key in dependencies:
        if _dependency_name_key(key) == target:
            return key
    return None


def _vendor_prefix(vendor_dir: Path, project_dir: Path) -> str:
    """Return the project-relative vendor directory prefix."""
    if vendor_dir.is_absolute():
        try:
            return vendor_dir.resolve().relative_to(project_dir.resolve()).as_posix()
        except ValueError:
            return vendor_dir.as_posix()
    return vendor_dir.as_posix()


def _download_wheel(
    name: str,
    version: str,
    source: str,
    vendor_dir: Path,
    trusted_hosts: list[str],
) -> tuple[Path, str]:
    """Download a wheel and return (target_path, parsed_version).

    Any existing wheels for the same package are removed first.
    Raises subprocess.CalledProcessError or RuntimeError on failure.
    """
    normalized_name = _normalize_package_name(name)

    for stale in vendor_dir.glob(f"{normalized_name}*.whl"):
        stale.unlink()

    with tempfile.TemporaryDirectory(dir=str(vendor_dir)) as tmp:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--no-deps",
            "--only-binary",
            ":all:",
            *_pip_trusted_host_args(source, trusted_hosts),
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
            raise RuntimeError("No wheel found")

        wheel = downloaded[0]
        _, parsed_version = _parse_wheel_filename(wheel.name)
        target_path = vendor_dir / wheel.name
        wheel.rename(target_path)
        return target_path, parsed_version


def _update_pyproject_paths(
    poetry: Any, vendor_dir: Path, lock: dict[str, Any]
) -> list[str]:
    """Update path dependencies in pyproject.toml to current wheel filenames.

    Returns the list of package names that were updated.
    """
    pyproject_path = poetry.file.path
    project_dir = pyproject_path.parent
    content = parse_toml(pyproject_path.read_text(encoding="utf-8"))
    dependencies = (
        content.get("tool", {}).get("poetry", {}).get("dependencies", {})
    )

    vendor_prefix_str = _vendor_prefix(vendor_dir, project_dir)
    vendor_prefixes = (
        f"{vendor_prefix_str}/",
        f"{vendor_dir}/",
    )

    updated: list[str] = []

    for name, info in lock.get("packages", {}).items():
        filename = info.get("filename")
        if not filename:
            continue

        dep_key = _find_dependency_key(dependencies, name)
        if dep_key is None:
            continue

        dep = dependencies[dep_key]
        if not isinstance(dep, dict):
            continue

        current_path = str(dep.get("path", ""))
        if any(current_path.startswith(prefix) for prefix in vendor_prefixes):
            dep["path"] = f"{vendor_prefix_str}/{filename}"
            updated.append(dep_key)

    if updated:
        pyproject_path.write_text(dumps_toml(content), encoding="utf-8")

    return updated


def _ensure_table(content: Any, *keys: str) -> Any:
    """Ensure a nested table exists in a tomlkit document, creating tables as needed."""
    current = content
    for key in keys:
        if key not in current:
            current[key] = {}
        current = current[key]
    return current


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

        trusted_hosts = vendor_config.get("trusted-hosts", [])
        if not isinstance(trusted_hosts, list):
            self.line_error(
                "<error>[tool.vendor] trusted-hosts must be a list of hostnames</error>"
            )
            return 1

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

            locked_pkg = lock["packages"].get(name)
            existing_wheel = (
                vendor_dir / locked_pkg["filename"]
                if locked_pkg and locked_pkg.get("filename")
                else None
            )

            self.line(f"<info>Processing {name}@{version}...</info>")

            if self.option("dry-run"):
                self.line(
                    f"  <comment>→ Would download {name}@{version} from {source}</comment>"
                )
                success_count += 1
                continue

            # Check if already vendored and not forced
            if (
                existing_wheel
                and existing_wheel.exists()
                and locked_pkg
                and not self.option("force")
            ):
                self.line(
                    f"  <info>✓ Already vendored: {name}=={locked_pkg['version']}</info>"
                )
                success_count += 1
                continue

            try:
                target_path, parsed_version = _download_wheel(
                    name, version, source, vendor_dir, trusted_hosts
                )
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

        if success_count > 0 and not self.option("dry-run") and fail_count == 0:
            updated = _update_pyproject_paths(poetry, vendor_dir, lock)
            if updated:
                self.line("")
                self.line(
                    "<comment>Updated path dependencies in pyproject.toml for:</comment>"
                )
                for dep in updated:
                    self.line(f"  <comment>• {dep}</comment>")
            else:
                self.line("")
                self.line(
                    "<comment>Remember to update your pyproject.toml dependencies to use path references:</comment>"
                )
                self.line(
                    '  <comment>my-package = { path = "vendor/my_package-1.0.0-py3-none-any.whl" }</comment>'
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

            for pkg_name, pkg_version in server_packages.items():
                expanded.append(
                    {
                        "name": pkg_name,
                        "source": source,
                        "version": str(pkg_version),
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
                wheel_path = vendor_dir / filename if filename else None

                if wheel_path and wheel_path.exists():
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


class VendorAddServerCommand(Command):
    """Register a vendor PyPI server in pyproject.toml."""

    name = "vendor add-server"
    description = "Add a vendor PyPI server to pyproject.toml"

    arguments = [
        argument("url", "Server URL"),
        argument("name", "Server name"),
    ]

    options = [
        option("trusted", "t", "Trust this host for plain HTTP indexes.", flag=True),
        option("force", "f", "Overwrite an existing server entry.", flag=True),
    ]

    def handle(self) -> int:
        url = self.argument("url")
        name = self.argument("name")

        if not url or not name:
            self.line_error("<error>Usage: poetry vendor add-server <url> <name></error>")
            return 1

        pyproject_path = self.poetry.file.path
        content = parse_toml(pyproject_path.read_text(encoding="utf-8"))

        vendor_table = _ensure_table(content, "tool", "vendor")
        servers = _ensure_table(vendor_table, "server")

        if name in servers and not self.option("force"):
            self.line_error(
                f"<error>Server '{name}' already exists. Use --force to overwrite.</error>"
            )
            return 1

        servers[name] = url

        if self.option("trusted"):
            trusted_hosts = vendor_table.get("trusted-hosts", [])
            if not isinstance(trusted_hosts, list):
                trusted_hosts = []
            host = _host_from_url(url)
            if host not in trusted_hosts:
                trusted_hosts.append(host)
            vendor_table["trusted-hosts"] = trusted_hosts

        pyproject_path.write_text(dumps_toml(content), encoding="utf-8")

        self.line(f"<info>Added server '{name}' = {url}</info>")
        if self.option("trusted"):
            self.line(
                f"<comment>Added {_host_from_url(url)} to trusted-hosts</comment>"
            )

        return 0


class VendorAddCommand(Command):
    """Add a package to the vendor configuration and download it."""

    name = "vendor add"
    description = "Add a package to vendor config, download it, and add a path dependency"

    arguments = [
        argument("package", "Package name"),
    ]

    options = [
        option("server", "s", "Server to use", flag=False),
        option("version", None, "Version specifier", flag=False),
        option("force", "f", "Overwrite an existing package entry.", flag=True),
    ]

    def handle(self) -> int:
        package = self.argument("package")
        server_name = self.option("server")
        version = self.option("version") or "*"

        if not package:
            self.line_error("<error>Usage: poetry vendor add <package> --server <server></error>")
            return 1

        if not server_name:
            self.line_error("<error>--server is required</error>")
            return 1

        poetry = self.poetry
        vendor_config = poetry.file.read().get("tool", {}).get("vendor", {})
        servers = vendor_config.get("server", {})
        source = servers.get(server_name)

        if source is None:
            self.line_error(
                f"<error>Unknown server '{server_name}'. Add it with 'poetry vendor add-server <url> {server_name}'</error>"
            )
            return 1

        vendor_dir = Path(vendor_config.get("vendor-dir", "vendor"))
        vendor_dir.mkdir(exist_ok=True)

        trusted_hosts = vendor_config.get("trusted-hosts", [])
        if not isinstance(trusted_hosts, list):
            trusted_hosts = []

        packages_table = vendor_config.get("packages", {})
        server_packages = packages_table.get(server_name, {})
        if package in server_packages and not self.option("force"):
            self.line_error(
                f"<error>Package '{package}' already configured for server '{server_name}'. Use --force to overwrite.</error>"
            )
            return 1

        self.line(f"<info>Downloading {package}@{version} from {server_name}...</info>")

        try:
            target_path, parsed_version = _download_wheel(
                package, version, source, vendor_dir, trusted_hosts
            )
        except subprocess.CalledProcessError as e:
            self.line_error(f"<error>Download failed: {e.stderr}</error>")
            return 1
        except Exception as e:
            self.line_error(f"<error>Error: {e}</error>")
            return 1

        # Update pyproject.toml
        pyproject_path = poetry.file.path
        project_dir = pyproject_path.parent
        content = parse_toml(pyproject_path.read_text(encoding="utf-8"))

        vendor_table = _ensure_table(content, "tool", "vendor")
        packages = _ensure_table(vendor_table, "packages")
        server_pkg_table = _ensure_table(packages, server_name)
        server_pkg_table[package] = version

        # Add/update path dependency
        dependencies = _ensure_table(content, "tool", "poetry", "dependencies")
        dep_key = _find_dependency_key(dependencies, package)
        if dep_key is None:
            dep_key = package

        dep = dependencies.get(dep_key)
        if not isinstance(dep, dict):
            dep = inline_table()
            dependencies[dep_key] = dep

        vendor_prefix_str = _vendor_prefix(vendor_dir, project_dir)
        dep["path"] = f"{vendor_prefix_str}/{target_path.name}"

        pyproject_path.write_text(dumps_toml(content), encoding="utf-8")

        # Update lock file
        lock = _read_lock(vendor_dir)
        lock["packages"] = dict(lock.get("packages", {}))
        lock["packages"][package] = {
            "version": parsed_version,
            "filename": target_path.name,
            "source": source,
            "requested": version,
        }
        _write_lock(vendor_dir, lock)

        self.line(
            f"<info>Added {package}=={parsed_version} from {server_name}</info>"
        )
        self.line(
            f"<comment>Updated pyproject.toml and vendor.lock. Run 'poetry lock' if needed.</comment>"
        )

        return 0
