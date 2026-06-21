"""Tests for vendor add and add-server commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from poetry_vendor_plugin.commands import VendorAddCommand, VendorAddServerCommand


def _build_add_server_command(
    fake_poetry: MagicMock, make_command_io: Any, argv: list[str]
) -> VendorAddServerCommand:
    command = VendorAddServerCommand()
    command._poetry = fake_poetry
    command._io = make_command_io(command, argv)
    return command


def _build_add_command(
    fake_poetry: MagicMock, make_command_io: Any, argv: list[str]
) -> VendorAddCommand:
    command = VendorAddCommand()
    command._poetry = fake_poetry
    command._io = make_command_io(command, argv)
    return command


def test_add_server_creates_config(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    command = _build_add_server_command(
        fake_poetry,
        make_command_io,
        ["poetry", "http://internal-pypi.local/simple/", "local"],
    )
    result = command.handle()

    assert result == 0
    content = fake_poetry.file.path.read_text(encoding="utf-8")
    assert "[tool.vendor.server]" in content
    assert 'local = "http://internal-pypi.local/simple/"' in content


def test_add_server_adds_trusted_host(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    command = _build_add_server_command(
        fake_poetry,
        make_command_io,
        [
            "poetry",
            "http://internal-pypi.local/simple/",
            "local",
            "--trusted",
        ],
    )
    result = command.handle()

    assert result == 0
    content = fake_poetry.file.path.read_text(encoding="utf-8")
    assert 'trusted-hosts = ["internal-pypi.local"]' in content


def test_add_server_refuses_duplicate(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    command = _build_add_server_command(
        fake_poetry,
        make_command_io,
        ["poetry", "http://example.com/simple/", "internal"],
    )
    result = command.handle()
    assert result == 1


def test_add_server_force_overwrites(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    command = _build_add_server_command(
        fake_poetry,
        make_command_io,
        [
            "poetry",
            "http://example.com/simple/",
            "internal",
            "--force",
        ],
    )
    result = command.handle()

    assert result == 0
    content = fake_poetry.file.path.read_text(encoding="utf-8")
    assert 'internal = "http://example.com/simple/"' in content


def _pip_download_mock(wheel_filename: str) -> Any:
    """Return a mock side-effect that simulates `pip download`."""

    def _side_effect(cmd, **kwargs):
        dest_idx = cmd.index("--dest") + 1
        dest = Path(cmd[dest_idx])
        dest.mkdir(parents=True, exist_ok=True)
        (dest / wheel_filename).write_bytes(b"PK\x03\x04" + b"\x00" * 20)

        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    return _side_effect


def test_add_package_downloads_and_updates_config(
    fake_poetry: MagicMock,
    vendor_dir: Path,
    make_command_io: Any,
) -> None:
    command = _build_add_command(
        fake_poetry,
        make_command_io,
        [
            "poetry",
            "another-package",
            "--server",
            "internal",
            "--version",
            "^1.0.0",
        ],
    )

    with patch(
        "poetry_vendor_plugin.commands.subprocess.run",
        side_effect=_pip_download_mock("another_package-1.2.0-py3-none-any.whl"),
    ):
        result = command.handle()

    assert result == 0

    content = fake_poetry.file.path.read_text(encoding="utf-8")
    assert 'another-package = "^1.0.0"' in content
    assert 'path = "vendor/another_package-1.2.0-py3-none-any.whl"' in content

    lock = json.loads((vendor_dir / "vendor.lock").read_text())
    assert lock["packages"]["another-package"]["version"] == "1.2.0"


def test_add_package_requires_server(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    command = _build_add_command(
        fake_poetry,
        make_command_io,
        ["poetry", "some-package"],
    )
    result = command.handle()
    assert result == 1


def test_add_package_refuses_duplicate(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    command = _build_add_command(
        fake_poetry,
        make_command_io,
        [
            "poetry",
            "my-build-tools",
            "--server",
            "internal",
        ],
    )
    result = command.handle()
    assert result == 1
