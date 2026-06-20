# Poetry Vendor Plugin — Example Project

This directory contains a minimal example project that shows how to use `poetry-vendor-plugin` to vendor packages from a private PyPI server.

To make the example runnable without setting up your own index, it uses the public **TestPyPI** server (`https://test.pypi.org/simple/`) and two small real packages: `six` and `colorama`.

## What it demonstrates

- Configuring one or more PyPI servers under `[tool.vendor.server]`.
- Declaring which packages come from which server under `[tool.vendor.packages.<server>]`.
- Using stable, version-less path dependencies in `[tool.poetry.dependencies]`.

## Prerequisites

- Poetry 2.0+

## Setup

### 1. Install the plugin

Poetry plugins must be installed in Poetry's own environment:

```bash
# Install from PyPI
poetry self add poetry-vendor-plugin

# Or install from the local source when developing this plugin
poetry self add ../
```

Verify it is loaded:

```bash
poetry self show plugins
```

### 2. Vendor the packages

From this directory:

```bash
poetry vendor pull
```

This downloads wheels from TestPyPI into `vendor/` and creates `vendor.lock`:

```
vendor/
├── six.whl
├── colorama.whl
└── vendor.lock
```

The wheel files use stable, version-less names, so the path dependencies in `pyproject.toml` do not need to change when versions are updated.

### 3. Install the project

Run this **after** vendoring, otherwise the path dependencies will fail because the wheels do not exist yet:

```bash
poetry install
```

### 4. Inspect or update vendored packages

```bash
# List vendored packages with resolved versions
poetry vendor list

# Update vendored packages to their latest allowed versions
poetry vendor update
```

## Adapting to a private PyPI server

Replace the TestPyPI URL in `pyproject.toml` with your internal index and swap `six`/`colorama` for your own internal packages:

```toml
[tool.vendor.server]
internal = "https://internal-pypi.company.local/simple/"

[tool.vendor.packages.internal]
my-build-tools = "^1.0.0"
my-ui-elements = ">=2.0.0,<3.0.0"
```

## Committing vendored packages

You should commit both the wheels and `vendor.lock` so that production or other developers have the exact same vendored packages:

```bash
git add vendor/
git commit -m "Vendor internal packages"
```

The included `vendor/.gitignore` ignores downloaded wheels by default, so you must explicitly `git add` the files you want to commit.
