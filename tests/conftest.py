"""Shared fixtures for command behavior tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from cleo.io.inputs.argv_input import ArgvInput
from cleo.io.io import IO
from cleo.io.outputs.buffered_output import BufferedOutput


@pytest.fixture
def vendor_dir(tmp_path: Path) -> Path:
    """Return a temporary vendor directory."""
    return tmp_path / "vendor"


@pytest.fixture
def fake_poetry(vendor_dir: Path) -> MagicMock:
    """Return a mock Poetry object with a [tool.poetry-vendor] config."""
    poetry: Any = MagicMock()
    poetry.file.read.return_value = {
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
    return poetry


@pytest.fixture
def make_command_io():
    """Return a helper that builds a bound IO for a given command."""

    def _make_command_io(command, argv: list[str] | None = None) -> IO:
        if argv is None:
            argv = ["poetry"]
        input_ = ArgvInput(argv)
        input_.bind(command.definition)
        return IO(input_, BufferedOutput(), BufferedOutput())

    return _make_command_io


@pytest.fixture
def make_fake_wheel():
    """Return a helper that creates a fake wheel file."""

    def _make_fake_wheel(directory: Path, filename: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        wheel = directory / filename
        wheel.write_bytes(b"PK\x03\x04" + b"\x00" * 20)
        return wheel

    return _make_fake_wheel
