"""Top-level Jobs registration for nautobot-app-phones.

Re-exports each integration's Job class so Nautobot's job-discovery
mechanism finds them via the conventional `jobs.py` path. Per-integration
modules are still where the Job logic lives — this file is just a thin
registration shim.
"""

from nautobot.apps.jobs import register_jobs

from nautobot_phones.integrations.cisco_ucm.jobs import CUCMDataSource
from nautobot_phones.integrations.freepbx.jobs import FreePBXDataSource

jobs = [CUCMDataSource, FreePBXDataSource]
register_jobs(*jobs)
