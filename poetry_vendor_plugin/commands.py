"""Commands for the Poetry Vendor Plugin."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from cleo.commands.command import Command
from cleo.helpers import option
from poetry.factory import Factory


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

        if not vendor_config:
            self.line_error(
                "<error>No [tool.poetry-vendor] configuration found in pyproject.toml</error>"
            )
            return 1

        vendor_dir = Path(vendor_config.get("vendor-dir", "vendor"))
        vendor_dir.mkdir(exist_ok=True)

        packages = vendor_config.get("packages", [])
        if not packages:
            self.line("<comment>No vendor packages configured.</comment>")
            return 0

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
                    f"<error>  ✗ Invalid config: missing name or source</error>"
                )
                fail_count += 1
                continue

            self.line(f"<info>Processing {name}@{version}...</info>")

            if self.option("dry-run"):
                self.line(f"  <comment>→ Would download from {source}</comment>")
                success_count += 1
                continue

            # Check if already vendored and not forced
            existing = list(vendor_dir.glob(f"{name.replace('-', '_')}*.whl"))
            if existing and not self.option("force"):
                self.line(f"  <info>✓ Already vendored: {existing[0].name}</info>")
                success_count += 1
                continue

            # Remove old versions if updating
            for old in vendor_dir.glob(f"{name.replace('-', '_')}*.whl"):
                old.unlink()
                self.line(f"  <comment>→ Removed old: {old.name}</comment>")

            # Download using pip
            try:
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
                    str(vendor_dir),
                    f"{name}{version}",
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                downloaded = list(vendor_dir.glob(f"{name.replace('-', '_')}*.whl"))
                if downloaded:
                    self.line(f"  <info>✓ Downloaded: {downloaded[-1].name}</info>")
                    success_count += 1
                else:
                    self.line_error(f"<error>  ✗ Download failed - no wheel found</error>")
                    fail_count += 1

            except subprocess.CalledProcessError as e:
                self.line_error(f"<error>  ✗ Download failed: {e.stderr}</error>")
                fail_count += 1
            except Exception as e:
                self.line_error(f"<error>  ✗ Error: {e}</error>")
                fail_count += 1

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
                '  <comment>my-package = { path = "vendor/my_package-1.0.0-py3-none-any.whl" }</comment>'
            )

        return 0 if fail_count == 0 else 1

    def _get_vendor_config(self, poetry: Any) -> dict[str, Any]:
        """Read vendor configuration from pyproject.toml."""
        pyproject = poetry.file.read()
        return pyproject.get("tool", {}).get("poetry-vendor", {})


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
        vendor_config = (
            poetry.file.read().get("tool", {}).get("poetry-vendor", {})
        )
        vendor_dir = Path(vendor_config.get("vendor-dir", "vendor"))

        if not vendor_dir.exists():
            self.line(
                "<comment>Vendor directory does not exist. Run 'poetry vendor pull' first.</comment>"
            )
            return 0

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

