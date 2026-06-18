# Poetry Vendor Plugin

Vendor internal packages from private PyPI repositories for offline/air-gapped production deployments.

## Why?

Your company has internal packages on a LAN-only PyPI server. Production servers have no access to it. This plugin downloads wheels to a `vendor/` folder so production can install without network access.

## Installation

```bash
poetry self add poetry-vendor-plugin
