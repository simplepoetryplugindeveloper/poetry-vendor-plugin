"""Tests for poetry-vendor-plugin commands."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from poetry_vendor_plugin.commands import (
    _dependency_name_key,
    _find_dependency_key,
    _host_from_url,
    _lock_file_path,
    _normalize_package_name,
    _parse_wheel_filename,
    _pip_requirement,
    _pip_trusted_host_args,
    _read_lock,
    _update_pyproject_paths,
    _write_lock,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("my-build-tools", "my_build_tools"),
        ("my_build_tools", "my_build_tools"),
        ("My.Build.Tools", "my_build_tools"),
        ("SomePackage", "somepackage"),
        ("a--b__c.d", "a_b_c_d"),
    ],
)
def test_normalize_package_name(name: str, expected: str) -> None:
    assert _normalize_package_name(name) == expected


@pytest.mark.parametrize(
    ("filename", "expected_name", "expected_version"),
    [
        (
            "my_build_tools-1.2.0-py3-none-any.whl",
            "my_build_tools",
            "1.2.0",
        ),
        (
            "some_package-2.1.0rc1-py2.py3-none-any.whl",
            "some_package",
            "2.1.0rc1",
        ),
        (
            "my_package-1.0.0-1-py3-none-any.whl",
            "my_package",
            "1.0.0",
        ),
    ],
)
def test_parse_wheel_filename(
    filename: str, expected_name: str, expected_version: str
) -> None:
    name, version = _parse_wheel_filename(filename)
    assert name == expected_name
    assert version == expected_version


def test_parse_wheel_filename_invalid() -> None:
    with pytest.raises(ValueError):
        _parse_wheel_filename("not-a-wheel.txt")

    with pytest.raises(ValueError):
        _parse_wheel_filename("invalid.whl")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("*", "six"),
        ("", "six"),
        ("^1.16.0", "six>=1.16.0,<2.0.0"),
        ("^0.4.6", "six>=0.4.6,<0.5.0"),
        ("~0.4.6", "six>=0.4.6,<0.5.0"),
        (">=2.0.0,<3.0.0", "six>=2.0.0,<3.0.0"),
        ("1.2.3", "six==1.2.3"),
        ("==1.2.3", "six==1.2.3"),
        ("!=1.2.3", "six!=1.2.3"),
    ],
)
def test_pip_requirement(version: str, expected: str) -> None:
    assert _pip_requirement("six", version) == expected


def test_dependency_name_key() -> None:
    assert _dependency_name_key("my-build-tools") == _dependency_name_key("my_build_tools")
    assert _dependency_name_key("My.Build.Tools") == _dependency_name_key("my_build_tools")


def test_find_dependency_key(tmp_path: Path) -> None:
    dependencies = {"my-build-tools": "^1.0.0", "requests": "^2.31"}
    assert _find_dependency_key(dependencies, "my-build-tools") == "my-build-tools"
    assert _find_dependency_key(dependencies, "my_build_tools") == "my-build-tools"
    assert _find_dependency_key(dependencies, "missing") is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://internal-pypi.local/simple/", "internal-pypi.local"),
        ("http://internal-pypi.local:8080/simple/", "internal-pypi.local:8080"),
        ("https://pypi.org/simple/", "pypi.org"),
    ],
)
def test_host_from_url(url: str, expected: str) -> None:
    assert _host_from_url(url) == expected


def test_pip_trusted_host_args() -> None:
    assert _pip_trusted_host_args(
        "http://internal-pypi.local/simple/", ["internal-pypi.local"]
    ) == ["--trusted-host", "internal-pypi.local"]
    assert _pip_trusted_host_args("https://pypi.org/simple/", ["internal-pypi.local"]) == []
    assert _pip_trusted_host_args("http://internal-pypi.local/simple/", []) == []


def test_update_pyproject_paths(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.31"
my-build-tools = { path = "vendor/my_build_tools-1.0.0-py3-none-any.whl" }
""",
        encoding="utf-8",
    )

    poetry = MagicMock()
    poetry.file.path = pyproject

    lock = {
        "packages": {
            "my-build-tools": {
                "filename": "my_build_tools-1.2.0-py3-none-any.whl",
            }
        }
    }

    updated = _update_pyproject_paths(poetry, Path("vendor"), lock)
    assert updated == ["my-build-tools"]

    content = pyproject.read_text(encoding="utf-8")
    assert 'path = "vendor/my_build_tools-1.2.0-py3-none-any.whl"' in content


def test_update_pyproject_paths_skips_non_vendor_paths(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[tool.poetry.dependencies]
python = "^3.11"
my-build-tools = { path = "../somewhere/my_build_tools.whl" }
""",
        encoding="utf-8",
    )

    poetry = MagicMock()
    poetry.file.path = pyproject

    lock = {
        "packages": {
            "my-build-tools": {
                "filename": "my_build_tools-1.2.0-py3-none-any.whl",
            }
        }
    }

    updated = _update_pyproject_paths(poetry, Path("vendor"), lock)
    assert updated == []

    content = pyproject.read_text(encoding="utf-8")
    assert "../somewhere/my_build_tools.whl" in content


def test_lock_file_roundtrip(tmp_path: Path) -> None:
    lock = {
        "version": 1,
        "packages": {
            "my-build-tools": {
                "version": "1.2.0",
                "filename": "my_build_tools-1.2.0-py3-none-any.whl",
                "source": "https://example.com/simple/",
                "requested": "^1.0.0",
            }
        },
    }

    _write_lock(tmp_path, lock)
    assert _lock_file_path(tmp_path).exists()

    read = _read_lock(tmp_path)
    assert read["version"] == 1
    assert read["packages"]["my-build-tools"]["version"] == "1.2.0"
    assert (
        read["packages"]["my-build-tools"]["filename"]
        == "my_build_tools-1.2.0-py3-none-any.whl"
    )


def test_read_lock_missing_returns_default(tmp_path: Path) -> None:
    lock = _read_lock(tmp_path)
    assert lock == {"version": 1, "packages": {}}


def test_read_lock_malformed_returns_default(tmp_path: Path) -> None:
    lock_path = tmp_path / "vendor.lock"
    lock_path.write_text("not valid json")
    lock = _read_lock(tmp_path)
    assert lock == {"version": 1, "packages": {}}
