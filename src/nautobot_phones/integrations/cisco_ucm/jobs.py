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
from nautobot.dcim.models import Location
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot_ssot.jobs.base import DataSource

from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter
from nautobot_phones.integrations.cisco_ucm.client import AXLClient
from nautobot_phones.integrations.cisco_ucm.risport import RISClient
from nautobot_phones.models import PhoneSystem


class CUCMDataSource(DataSource):
    """Sync a Cisco UCM cluster into Nautobot."""

    # Note: parent DataSource already provides `dryrun` (no underscore); we
    # don't redeclare it. Was a copy-paste from sibling plugins that caused
    # the form to render two "Dry run" checkboxes side-by-side.

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
    enrich_phone_ip = BooleanVar(
        default=False,
        description=(
            "Pull live IP addresses + registration status via RisPort70. Single "
            "bulk call (paginated), typically a few seconds. Cheap; recommended."
        ),
    )
    enrich_phone_devices = BooleanVar(
        default=False,
        description=(
            "Auto-create Nautobot Device records for each Phone, with Manufacturer "
            "(Cisco), DeviceType (from CCM model), and Network/PC/Voice Interfaces. "
            "Lets you cable Phones to switch ports / patch panels. Phones with no "
            "Location (and no fallback below) are skipped."
        ),
    )
    default_phone_location = ObjectVar(
        model=Location,
        required=False,
        description=(
            "Fallback Location for auto-created Phone Devices when neither the "
            "Phone record nor its PhoneSystem has one set. Skipped if blank and "
            "no other Location is found."
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
        ris_client = RISClient(
            host=ps.hostname,
            username=username,
            password=password,
            verify_tls=self.verify_tls,
        ) if self.enrich_phone_ip else None
        self.source_adapter = CUCMSourceAdapter(
            client=client,
            ris_client=ris_client,
            phone_system_record=ps,
            job=self,
            sync=self.sync,
            enrich_phone_lines=self.enrich_phone_lines,
            enrich_phone_ip=self.enrich_phone_ip,
        )
        self.source_adapter.load()

    def load_target_adapter(self) -> None:
        """Build the Nautobot-side adapter."""
        # Pair with source adapter's enrich_phone_lines flag — both must
        # agree on whether Line participates in the diff, otherwise dest
        # records get orphan-deleted when source isn't enriching.
        self.target_adapter = PhonesNautobotAdapter(
            job=self,
            sync=self.sync,
            include_lines=self.enrich_phone_lines,
        )
        self.target_adapter.load()

    def execute_sync(self) -> None:
        """After the standard DiffSync flow, optionally auto-create Devices."""
        super().execute_sync()
        if not self.enrich_phone_devices or self.dryrun:
            return
        from nautobot_phones.integrations.cisco_ucm.devices import (
            enrich_analog_gateway_devices,
            enrich_phone_devices,
        )
        # Phase 1: phones → DCIM Devices (auto-creates, since each Phone is
        # uniquely identified by MAC).
        result = enrich_phone_devices(
            default_location=self.default_phone_location,
            logger=self.logger,
        )
        self.logger.info(
            "Phone-Device enrichment: created=%d, skipped_already_linked=%d, "
            "skipped_no_location=%d, errored=%d",
            result["created"],
            result["skipped_already_linked"],
            result["skipped_no_location"],
            result["errored"],
        )
        # Phase 2: AnalogGateways → existing DCIM Devices (matches only,
        # never creates — DCIM is the authority for gateway hardware).
        gw_result = enrich_analog_gateway_devices(logger=self.logger)
        self.logger.info(
            "AnalogGateway-Device matching: matched_exact=%d, matched_mac_base=%d, "
            "matched_unique_dt=%d, skipped_already_linked=%d, unmatched=%d",
            gw_result["matched_exact"],
            gw_result["matched_mac_base"],
            gw_result["matched_unique_dt"],
            gw_result["skipped_already_linked"],
            gw_result["unmatched"],
        )


jobs = [CUCMDataSource]
register_jobs(*jobs)
