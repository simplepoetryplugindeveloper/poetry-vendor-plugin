# Poetry Vendor Plugin — Example Project

This directory contains a minimal example project that shows how to use `poetry-vendor-plugin` to vendor packages from a private PyPI server.

To make the example runnable without setting up your own index, it uses the public **TestPyPI** server (`https://test.pypi.org/simple/`) and two small real packages: `six` and `colorama`.

## What it demonstrates

- Configuring one or more PyPI servers under `[tool.vendor.server]`.
- Declaring which packages come from which server under `[tool.vendor.packages.<server>]`.
- Using path dependencies in `[tool.poetry.dependencies]` that point to the vendored wheels.

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

### 2. Configure servers and packages

You can edit `pyproject.toml` directly, or use the convenience commands:

```bash
# Register the TestPyPI server
poetry vendor add-server https://test.pypi.org/simple/ testpypi

# Add packages from that server
poetry vendor add six --server testpypi --version "^1.16.0"
poetry vendor add colorama --server testpypi --version "^0.4.6"
```

### HTTP / internal indexes

If your private PyPI server uses plain HTTP (not HTTPS), pip will refuse to use it by default. Register the server with `--trusted`:

```bash
poetry vendor add-server http://192.168.1.10/simple/ internal --trusted
```

### 2. Vendor the packages

From this directory:

```bash
poetry vendor pull
```

This downloads wheels from TestPyPI into `vendor/` with their original versioned filenames and creates `vendor.lock`:

```
vendor/
├── six-1.16.0-py2.py3-none-any.whl
├── colorama-0.4.6-py2.py3-none-any.whl
└── vendor.lock
```

`poetry vendor pull` automatically updates the path dependencies in `pyproject.toml` to match the downloaded wheel filenames.

### 3. Lock and install

After vendoring, regenerate the lock file so Poetry sees the updated path dependencies, then install:

```bash
poetry lock
poetry install
```

The example sets `package-mode = false` in `pyproject.toml` so Poetry only installs dependencies, not a package.

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

The included `.gitignore` ignores downloaded wheels by default, so you must explicitly `git add` the files you want to commit.
