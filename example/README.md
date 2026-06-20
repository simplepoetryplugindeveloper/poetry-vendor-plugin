# Poetry Vendor Plugin — Example Project

This directory contains a minimal example project that shows how to use `poetry-vendor-plugin` to vendor internal packages from a private PyPI server.

## What it demonstrates

- Configuring one or more private PyPI servers under `[tool.vendor.server]`.
- Declaring which packages come from which server under `[tool.vendor.packages.<server>]`.
- Using stable, version-less path dependencies in `[tool.poetry.dependencies]`.

## Prerequisites

- Poetry 2.0+
- The plugin installed in Poetry:
  ```bash
  poetry self add poetry-vendor-plugin
  ```
- Access to the private PyPI server(s) configured in `pyproject.toml`.

> The server URL in this example (`https://internal-pypi.company.local/simple/`) is a placeholder. Replace it with your real index URL before running the commands.

## Usage

From this directory:

```bash
# Download vendor packages into vendor/ and create vendor.lock
poetry vendor pull

# List vendored packages with resolved versions
poetry vendor list

# Update vendored packages to their latest allowed versions
poetry vendor update
```

After running `poetry vendor pull`, the `vendor/` directory will contain:

```
vendor/
├── my_build_tools.whl
├── my_ui_elements.whl
└── vendor.lock
```

The wheel files use stable, version-less names, so the path dependencies in `pyproject.toml` do not need to change when versions are updated.

## Committing vendored packages

You should commit both the wheels and `vendor.lock` so that production or other developers have the exact same vendored packages:

```bash
git add vendor/
git commit -m "Vendor internal packages"
```

The included `vendor/.gitignore` ignores downloaded wheels by default, so you must explicitly `git add` the files you want to commit.
