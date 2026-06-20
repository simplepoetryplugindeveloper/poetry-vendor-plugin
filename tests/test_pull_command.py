"""Behavior tests for VendorPullCommand."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from poetry_vendor_plugin.commands import VendorPullCommand


def _pip_download_mock(wheel_filename: str) -> Any:
    """Return a mock side-effect that simulates `pip download`.

    It creates the requested wheel in the directory specified by `--dest`.
    """

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


def _build_command(fake_poetry: MagicMock, make_command_io: Any, argv: list[str] | None = None) -> VendorPullCommand:
    command = VendorPullCommand()
    command.poetry = fake_poetry
    command._io = make_command_io(command, argv)
    return command


def test_pull_downloads_and_renames_wheel(
    fake_poetry: MagicMock, vendor_dir: Path, make_command_io: Any
) -> None:
    command = _build_command(fake_poetry, make_command_io)

    with patch(
        "poetry_vendor_plugin.commands.subprocess.run",
        side_effect=_pip_download_mock("my_build_tools-1.2.0-py3-none-any.whl"),
    ) as mock_run:
        result = command.handle()

    assert result == 0
    assert (vendor_dir / "my_build_tools.whl").exists()
    mock_run.assert_called_once()

    lock = json.loads((vendor_dir / "vendor.lock").read_text())
    assert lock["packages"]["my-build-tools"]["version"] == "1.2.0"
    assert lock["packages"]["my-build-tools"]["filename"] == "my_build_tools.whl"


def test_pull_skips_existing_when_not_forced(
    fake_poetry: MagicMock,
    vendor_dir: Path,
    make_command_io: Any,
    make_fake_wheel: Any,
) -> None:
    make_fake_wheel(vendor_dir, "my_build_tools.whl")
    lock = {
        "version": 1,
        "packages": {
            "my-build-tools": {
                "version": "1.2.0",
                "filename": "my_build_tools.whl",
                "source": "https://example.com/simple/",
                "requested": "^1.0.0",
            }
        },
    }
    (vendor_dir / "vendor.lock").write_text(json.dumps(lock))

    command = _build_command(fake_poetry, make_command_io)

    with patch("poetry_vendor_plugin.commands.subprocess.run") as mock_run:
        result = command.handle()

    assert result == 0
    mock_run.assert_not_called()


def test_pull_force_redownloads(
    fake_poetry: MagicMock,
    vendor_dir: Path,
    make_command_io: Any,
    make_fake_wheel: Any,
) -> None:
    make_fake_wheel(vendor_dir, "my_build_tools.whl")
    old_lock = {
        "version": 1,
        "packages": {
            "my-build-tools": {
                "version": "0.9.0",
                "filename": "my_build_tools.whl",
                "source": "https://example.com/simple/",
                "requested": "^1.0.0",
            }
        },
    }
    (vendor_dir / "vendor.lock").write_text(json.dumps(old_lock))

    command = _build_command(fake_poetry, make_command_io, argv=["poetry", "--force"])

    with patch(
        "poetry_vendor_plugin.commands.subprocess.run",
        side_effect=_pip_download_mock("my_build_tools-1.5.0-py3-none-any.whl"),
    ):
        result = command.handle()

    assert result == 0
    lock = json.loads((vendor_dir / "vendor.lock").read_text())
    assert lock["packages"]["my-build-tools"]["version"] == "1.5.0"


def test_pull_dry_run(
    fake_poetry: MagicMock, vendor_dir: Path, make_command_io: Any
) -> None:
    command = _build_command(fake_poetry, make_command_io, argv=["poetry", "--dry-run"])

    with patch("poetry_vendor_plugin.commands.subprocess.run") as mock_run:
        result = command.handle()

    assert result == 0
    mock_run.assert_not_called()
    assert not (vendor_dir / "my_build_tools.whl").exists()
    assert not (vendor_dir / "vendor.lock").exists()


def test_pull_no_config_returns_error(
    fake_poetry: MagicMock, make_command_io: Any
) -> None:
    fake_poetry.file.read.return_value = {"tool": {}}
    command = _build_command(fake_poetry, make_command_io)

    with patch("poetry_vendor_plugin.commands.subprocess.run") as mock_run:
        result = command.handle()

    assert result == 1
    mock_run.assert_not_called()


def test_pull_deprecated_config_returns_error(
    fake_poetry: MagicMock, vendor_dir: Path, make_command_io: Any
) -> None:
    fake_poetry.file.read.return_value = {
        "tool": {
            "poetry-vendor": {
                "vendor-dir": str(vendor_dir),
                "packages": [
                    {
                        "name": "my-build-tools",
                        "source": "https://example.com/simple/",
                        "version": "^1.0.0",
                    }
                ],
            }
        }
    }
    command = _build_command(fake_poetry, make_command_io)

    with patch("poetry_vendor_plugin.commands.subprocess.run") as mock_run:
        result = command.handle()

    assert result == 1
    mock_run.assert_not_called()


def test_pull_invalid_package_config(
    fake_poetry: MagicMock, vendor_dir: Path, make_command_io: Any
) -> None:
    fake_poetry.file.read.return_value = {
        "tool": {
            "vendor": {
                "vendor-dir": str(vendor_dir),
                "server": {
                    "internal": "https://example.com/simple/",
                },
                "packages": {
                    "unknown-server": {  # server not defined in [tool.vendor.server]
                        "my-build-tools": "^1.0.0",
                    }
                },
            }
        }
    }
    command = _build_command(fake_poetry, make_command_io)

    with patch("poetry_vendor_plugin.commands.subprocess.run") as mock_run:
        result = command.handle()

    assert result == 1
    mock_run.assert_not_called()
