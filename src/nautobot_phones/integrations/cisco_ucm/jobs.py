"""SSoT Job for syncing a Cisco UCM cluster into Nautobot.

`CUCMDataSource` subclasses `nautobot_ssot.jobs.base.DataSource` — that's
the read-from-vendor-into-Nautobot direction (inverted from
sibling-project ssot-hudu which uses `DataTarget`).

The Job:
  1. Resolves AXL credentials from the PhoneSystem's SecretsGroup.
  2. Builds an AXLClient.
  3. Constructs the source adapter (CUCMSourceAdapter wrapping the client).
  4. Constructs the destination adapter (PhonesNautobotAdapter, scoped by
     the chosen PhoneSystem).
  5. DiffSync's framework computes + optionally applies the diff.

In dry_run mode the diff is logged but not written. Use this to preview
what would change before kicking off a real sync.
"""

from __future__ import annotations

import os

from nautobot.apps.jobs import BooleanVar, ObjectVar, register_jobs
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot_ssot.jobs.base import DataSource

from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter
from nautobot_phones.integrations.cisco_ucm.client import AXLClient
from nautobot_phones.models import PhoneSystem


class CUCMDataSource(DataSource):
    """Sync a Cisco UCM cluster into Nautobot."""

    dry_run = BooleanVar(
        default=True,
        description="Calculate the diff but do not write to Nautobot.",
    )
    phone_system = ObjectVar(
        model=PhoneSystem,
        query_params={"vendor": "cisco_ucm"},
        description="Cisco UCM cluster to sync. Must have secrets_group + hostname populated.",
    )
    verify_tls = BooleanVar(
        default=True,
        description="Verify the publisher's TLS certificate (disable for self-signed dev clusters).",
    )
    enrich_phone_lines = BooleanVar(
        default=False,
        description=(
            "Pull per-phone line membership via getPhone. Slow — adds ~200-400ms "
            "per phone (5-10 min for 1000+ phones). Off by default."
        ),
    )

    class Meta:
        """Job metadata."""

        name = "Cisco UCM -> Nautobot"
        description = "Mirror a CUCM cluster's phones, DNs, trunks, and dial-plan into Nautobot."
        data_source = "Cisco UCM"
        data_target = "Nautobot"

    def load_source_adapter(self) -> None:
        """Build the AXL client from secrets, instantiate the CUCM adapter."""
        ps = self.phone_system
        if not ps.hostname:
            raise ValueError(f"PhoneSystem {ps.name!r} has no hostname configured.")
        if not ps.secrets_group:
            raise ValueError(f"PhoneSystem {ps.name!r} has no secrets_group configured.")

        # Resolve credentials from SecretsGroup. Convention: HTTP access type,
        # USERNAME + PASSWORD secret types.
        username = ps.secrets_group.get_secret_value(
            SecretsGroupAccessTypeChoices.TYPE_HTTP,
            SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        password = ps.secrets_group.get_secret_value(
            SecretsGroupAccessTypeChoices.TYPE_HTTP,
            SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )

        client = AXLClient(
            host=ps.hostname,
            username=username,
            password=password,
            version=os.environ.get("AXL_VERSION", "15.0"),
            verify_tls=self.verify_tls,
        )
        self.source_adapter = CUCMSourceAdapter(
            client=client,
            phone_system_record=ps,
            job=self,
            sync=self.sync,
            enrich_phone_lines=self.enrich_phone_lines,
        )
        self.source_adapter.load()

    def load_target_adapter(self) -> None:
        """Build the Nautobot-side adapter."""
        self.target_adapter = PhonesNautobotAdapter(job=self, sync=self.sync)
        self.target_adapter.load()


jobs = [CUCMDataSource]
register_jobs(*jobs)
