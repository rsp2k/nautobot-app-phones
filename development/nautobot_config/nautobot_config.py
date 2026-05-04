"""Nautobot config for the nautobot-app-phones dev stack.

Loaded via volume mount at /opt/nautobot/nautobot_config.py inside each
Nautobot container. Imports the upstream defaults, then overrides only
what we need: PLUGINS, PLUGINS_CONFIG, and a couple of dev toggles.

Note: nautobot_phones has no plugin-level globals — connection config and
secrets live on each PhoneSystem record. PLUGINS_CONFIG['nautobot_phones']
is intentionally empty.
"""

import os

# Pull in Nautobot's default settings (DB/cache/Celery wiring from env vars).
from nautobot.core.settings import *  # noqa: F401,F403
from nautobot.core.settings_funcs import is_truthy  # noqa: F401

DEBUG = is_truthy(os.environ.get("NAUTOBOT_DEBUG", "true"))

PLUGINS = [
    "nautobot_ssot",
    "nautobot_phones",
]

PLUGINS_CONFIG = {
    "nautobot_ssot": {
        "hide_example_jobs": False,
    },
    "nautobot_phones": {},
}
