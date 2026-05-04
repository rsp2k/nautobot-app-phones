"""Nautobot app for multi-vendor campus phone-system inventory.

Mirrors Cisco UCM (via AXL) and FreePBX into a unified Nautobot data model:
phones, directory numbers, DIDs, trunks, ATAs, analog gateways, and dial-plan
structure (partitions, calling search spaces, route patterns).

Sync is one-way (vendor -> Nautobot, read-only mirror). The phone system is
authoritative; this app reflects its state.
"""

from importlib.metadata import PackageNotFoundError, version

from nautobot.apps import NautobotAppConfig

try:
    __version__ = version("nautobot-app-phones")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"


class NautobotPhonesConfig(NautobotAppConfig):
    """App configuration for nautobot-app-phones."""

    name = "nautobot_phones"
    verbose_name = "Phones"
    description = "Multi-vendor campus phone-system inventory (Cisco UCM, FreePBX)."
    version = __version__
    author = "Ryan Malloy"
    author_email = "ryan@supported.systems"
    base_url = "phones"
    required_settings: list[str] = []
    default_settings: dict = {}
    caching_config: dict = {}


config = NautobotPhonesConfig
