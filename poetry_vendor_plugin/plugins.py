"""Plugin entry point for Poetry Vendor Plugin."""

from poetry.console.application import Application
from poetry.plugins.application_plugin import ApplicationPlugin

from poetry_vendor_plugin.commands import (
    VendorAddCommand,
    VendorAddServerCommand,
    VendorListCommand,
    VendorPullCommand,
    VendorUpdateCommand,
)


class VendorPlugin(ApplicationPlugin):
    """Plugin that adds vendor management commands to Poetry."""

    def activate(self, application: Application) -> None:
        application.command_loader.register_factory(
            "vendor pull", lambda: VendorPullCommand()
        )
        application.command_loader.register_factory(
            "vendor update", lambda: VendorUpdateCommand()
        )
        application.command_loader.register_factory(
            "vendor list", lambda: VendorListCommand()
        )
        application.command_loader.register_factory(
            "vendor add-server", lambda: VendorAddServerCommand()
        )
        application.command_loader.register_factory(
            "vendor add", lambda: VendorAddCommand()
        )
