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
def fake_poetry(vendor_dir: Path, tmp_path: Path) -> MagicMock:
    """Return a mock Poetry object with a [tool.poetry-vendor] config."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.poetry]
name = "test-project"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
my-build-tools = { path = "vendor/my_build_tools-1.0.0-py3-none-any.whl" }

[tool.vendor]
vendor-dir = "vendor"

[tool.vendor.server]
internal = "https://example.com/simple/"

[tool.vendor.packages.internal]
my-build-tools = "^1.0.0"
""",
        encoding="utf-8",
    )

    poetry: Any = MagicMock()
    poetry.file.path = pyproject
    poetry.file.read.return_value = {
        "tool": {
            "vendor": {
                "vendor-dir": str(vendor_dir),
                "server": {
                    "internal": "https://example.com/simple/",
                },
                "packages": {
                    "internal": {
                        "my-build-tools": "^1.0.0",
                    }
                },
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
