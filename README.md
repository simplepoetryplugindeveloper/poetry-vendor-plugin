# Poetry Vendor Plugin

[![PyPI version](https://badge.fury.io/py/poetry-vendor-plugin.svg)](https://pypi.org/project/poetry-vendor-plugin/)
[![Python versions](https://img.shields.io/pypi/pyversions/poetry-vendor-plugin.svg)](https://pypi.org/project/poetry-vendor-plugin/)

Vendor internal packages from private PyPI repositories for offline/air-gapped production deployments.

## The Problem

You have internal Python packages hosted on a PyPI server inside your company LAN. Development machines can reach it, but production servers cannot (either air-gapped or on a different network). You need a way to bundle those internal packages as wheels into your project so production can install them without network access.

## The Solution

This plugin adds `poetry vendor pull` — a command that downloads your configured internal packages as wheels into a `vendor/` directory. You commit those wheels, and production installs from them using Poetry path dependencies.

## Installation

Poetry plugins are installed into Poetry's own environment:

```bash
poetry self add poetry-vendor-plugin
```

Verify the plugin is loaded:

```bash
poetry self show plugins
```

## Example

See the [`example/`](example/) directory for a complete, runnable project that configures one private PyPI server and two vendored packages.

## Usage

### 1. Configure vendor packages in your project

Add to your project's `pyproject.toml`:

```toml
[tool.vendor]
vendor-dir = "vendor"

[tool.vendor.server]
internal = "https://internal-pypi.company.local/simple/"

[tool.vendor.packages.internal]
my-build-tools = "^1.0.0"
my-ui-elements = ">=2.0.0,<3.0.0"
```

### 2. Pull vendor packages

```bash
poetry vendor pull
```

This downloads wheels to `vendor/`:

```
vendor/
├── my_build_tools.whl
├── my_ui_elements.whl
└── vendor.lock
```

The wheel files use stable, version-less names, and `vendor.lock` records the resolved versions. Commit both the wheels and the lock file.

### 3. Use path dependencies in production

In your `pyproject.toml`, switch to path dependencies for production builds:

```toml
[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.31"
my-build-tools = { path = "vendor/my_build_tools.whl" }
my-ui-elements = { path = "vendor/my_ui_elements.whl" }
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
[tool.vendor]
vendor-dir = "vendor"  # Directory for vendored wheels (default: "vendor")

[tool.vendor.server]
server1 = "https://..."  # Named private PyPI index URL

[tool.vendor.packages.server1]
package-name = "^1.0.0"  # Package name and PEP 440 version specifier
```

You can define multiple servers and group packages under the server they come from:

```toml
[tool.vendor.server]
internal = "https://internal-pypi.company.local/simple/"
legacy = "https://legacy-pypi.company.local/simple/"

[tool.vendor.packages.internal]
my-build-tools = "^1.0.0"

[tool.vendor.packages.legacy]
old-ui-elements = ">=1.0.0,<2.0.0"
```

## Lock File

After running `poetry vendor pull`, a `<vendor-dir>/vendor.lock` file is created. It tracks the resolved version, source, and requested version specifier for each package. Commit this file alongside the wheels so that `poetry vendor list` can show accurate version information and so updates behave predictably across machines.

## Requirements

- Python 3.9+
- Poetry 2.0+

## License

MIT
