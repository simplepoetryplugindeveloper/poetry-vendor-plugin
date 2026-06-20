"""Tests for poetry-vendor-plugin commands."""

from pathlib import Path

import pytest

from poetry_vendor_plugin.commands import (
    _lock_file_path,
    _normalize_package_name,
    _parse_wheel_filename,
    _read_lock,
    _target_wheel_path,
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


def test_target_wheel_path(tmp_path: Path) -> None:
    assert _target_wheel_path(tmp_path, "my-build-tools") == tmp_path / "my_build_tools.whl"


def test_lock_file_roundtrip(tmp_path: Path) -> None:
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

    _write_lock(tmp_path, lock)
    assert _lock_file_path(tmp_path).exists()

    read = _read_lock(tmp_path)
    assert read["version"] == 1
    assert read["packages"]["my-build-tools"]["version"] == "1.2.0"
    assert read["packages"]["my-build-tools"]["filename"] == "my_build_tools.whl"


def test_read_lock_missing_returns_default(tmp_path: Path) -> None:
    lock = _read_lock(tmp_path)
    assert lock == {"version": 1, "packages": {}}


def test_read_lock_malformed_returns_default(tmp_path: Path) -> None:
    lock_path = tmp_path / "vendor.lock"
    lock_path.write_text("not valid json")
    lock = _read_lock(tmp_path)
    assert lock == {"version": 1, "packages": {}}
