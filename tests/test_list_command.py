"""Behavior tests for VendorListCommand."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from poetry_vendor_plugin.commands import VendorListCommand


def _build_command(fake_poetry: MagicMock, make_command_io: Any) -> VendorListCommand:
    command = VendorListCommand()
    command._poetry = fake_poetry
    command._io = make_command_io(command)
    return command


def test_list_reads_from_lock_file(
    fake_poetry: MagicMock,
    vendor_dir: Any,
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
    result = command.handle()

    assert result == 0
    output = command._io.output.fetch()
    assert "my-build-tools==1.2.0" in output


def test_list_fallback_without_lock(
    fake_poetry: MagicMock,
    vendor_dir: Any,
    make_command_io: Any,
    make_fake_wheel: Any,
) -> None:
    make_fake_wheel(vendor_dir, "my_build_tools.whl")

    command = _build_command(fake_poetry, make_command_io)
    result = command.handle()

    assert result == 0
    output = command._io.output.fetch()
    assert "my_build_tools.whl" in output


def test_list_missing_vendor_dir(
    fake_poetry: MagicMock, vendor_dir: Any, make_command_io: Any
) -> None:
    # Ensure the directory does not exist
    assert not vendor_dir.exists()

    command = _build_command(fake_poetry, make_command_io)
    result = command.handle()

    assert result == 0
    output = command._io.output.fetch()
    assert "Run 'poetry vendor pull' first" in output
