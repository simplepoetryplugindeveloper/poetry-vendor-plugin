# Poetry Vendor Plugin

[![PyPI version](https://badge.fury.io/py/poetry-vendor-plugin.svg)](https://pypi.org/project/poetry-vendor-plugin/)
[![Python versions](https://img.shields.io/pypi/pyversions/poetry-vendor-plugin.svg)](https://pypi.org/project/poetry-vendor-plugin/)

Vendor internal packages from private PyPI repositories for offline/air-gapped production deployments.

## The Problem

You have internal Python packages hosted on a PyPI server inside your company LAN. Development machines can reach it, but production servers cannot (either air-gapped or on a different network). You need a way to bundle those internal packages as wheels into your project so production can install them without network access.

## The Solution

This plugin adds `poetry vendor pull` — a command that downloads your configured internal packages as wheels into a `vendor/` directory. You commit those wheels, and production installs from them using Poetry path dependencies.

## Installation

```bash
poetry self add poetry-vendor-plugin
```

## Usage

### 1. Configure vendor packages in your project

Add to your project's `pyproject.toml`:

```toml
[tool.poetry-vendor]
vendor-dir = "vendor"

[[tool.poetry-vendor.packages]]
name = "my-build-tools"
source = "https://internal-pypi.company.local/simple/"
version = "^1.0.0"

[[tool.poetry-vendor.packages]]
name = "my-ui-elements"
source = "https://internal-pypi.company.local/simple/"
version = ">=2.0.0,<3.0.0"
```

### 2. Pull vendor packages

```bash
poetry vendor pull
```

This downloads wheels to `vendor/`:

```
vendor/
├── my_build_tools-1.2.0-py3-none-any.whl
└── my_ui_elements-2.1.0-py3-none-any.whl
```

### 3. Use path dependencies in production

In your `pyproject.toml`, switch to path dependencies for production builds:

```toml
[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.31"
my-build-tools = { path = "vendor/my_build_tools-1.2.0-py3-none-any.whl" }
my-ui-elements = { path = "vendor/my_ui_elements-2.1.0-py3-none-any.whl" }
```

### 4. List vendored packages

```bash
poetry vendor list
```

### 5. Update vendor packages

```bash
poetry vendor update          # Update all
poetry vendor update -p my-build-tools  # Update specific package
```

## Commands

| Command | Description |
|---------|-------------|
| `poetry vendor pull` | Download vendor packages to `vendor/` |
| `poetry vendor pull --force` | Re-download even if already present |
| `poetry vendor pull --dry-run` | Preview what would be downloaded |
| `poetry vendor list` | Show all vendored packages with sizes |
| `poetry vendor update` | Force re-download all packages |

## Configuration Reference

```toml
[tool.poetry-vendor]
vendor-dir = "vendor"  # Directory for vendored wheels (default: "vendor")

[[tool.poetry-vendor.packages]]
name = "package-name"     # Package name on PyPI
source = "https://..."    # Private PyPI index URL
version = "^1.0.0"        # Version specifier (any PEP 440 specifier)
```

## Requirements

- Python 3.9+
- Poetry 2.0+

## License

MIT
