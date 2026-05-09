"""SSoT Job for syncing a FreePBX cluster into Nautobot.

`FreePBXDataSource` mirrors `CUCMDataSource` in shape — DataSource (not
DataTarget), uses an ObjectVar to pick the PhoneSystem record, drives a
source-adapter / target-adapter pair through DiffSync's standard flow.

Authentication: FreePBX 17's GraphQL uses OAuth2 client_credentials.
The `client_id` + `client_secret` come from FreePBX Admin > API >
Applications and live in the PhoneSystem's SecretsGroup as the standard
USERNAME / PASSWORD pair (we treat client_id as the "username" slot for
schema reuse with the CCM job — saves us from inventing yet-another
secret-type vocabulary).

Status: SCAFFOLD. The Job class is registered and resolves credentials,
but `load_source_adapter` will currently raise NotImplementedError when
the adapter's `_load_extensions` runs (stage 4 fills that in).
"""

from __future__ import annotations

from nautobot.apps.jobs import BooleanVar, ObjectVar, register_jobs
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot_ssot.jobs.base import DataSource

from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
from nautobot_phones.integrations.freepbx.adapter import FreePBXSourceAdapter
from nautobot_phones.integrations.freepbx.client import FreePBXClient
from nautobot_phones.models import PhoneSystem


class FreePBXDataSource(DataSource):
    """Sync a FreePBX system into Nautobot."""

    phone_system = ObjectVar(
        model=PhoneSystem,
        query_params={"vendor": "freepbx"},
        description="FreePBX system to sync. Must have secrets_group + hostname populated.",
    )
    verify_tls = BooleanVar(
        default=True,
        description=(
            "Verify the FreePBX TLS certificate (disable for self-signed dev "
            "installs — the local dev container uses HTTP and ignores this)."
        ),
    )

    class Meta:
        """Job metadata."""

        name = "FreePBX -> Nautobot"
        description = "Mirror a FreePBX system's extensions, trunks, and dial-plan into Nautobot."
        data_source = "FreePBX"
        data_target = "Nautobot"

    def load_source_adapter(self) -> None:
        """Build the FreePBX client from secrets, instantiate the adapter."""
        ps = self.phone_system
        if not ps.hostname:
            raise ValueError(f"PhoneSystem {ps.name!r} has no hostname configured.")
        if not ps.secrets_group:
            raise ValueError(f"PhoneSystem {ps.name!r} has no secrets_group configured.")

        # FreePBX hostname can be either bare host (e.g. "freepbx") or full
        # URL (e.g. "https://pbx.example.com"). Normalize to a base URL.
        base_url = ps.hostname
        if not base_url.startswith(("http://", "https://")):
            scheme = "http" if not self.verify_tls else "https"
            base_url = f"{scheme}://{base_url}"

        # Resolve OAuth2 credentials from SecretsGroup. We reuse the HTTP
        # USERNAME slot for `client_id` and PASSWORD for `client_secret`
        # so operators don't have to learn a per-vendor secret-type
        # vocabulary — same SecretsGroup shape works for CCM and FreePBX.
        client_id = ps.secrets_group.get_secret_value(
            SecretsGroupAccessTypeChoices.TYPE_HTTP,
            SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        client_secret = ps.secrets_group.get_secret_value(
            SecretsGroupAccessTypeChoices.TYPE_HTTP,
            SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )

        client = FreePBXClient(
            base_url=base_url,
            client_id=client_id,
            client_secret=client_secret,
            verify_tls=self.verify_tls,
        )
        self.source_adapter = FreePBXSourceAdapter(
            client=client,
            phone_system_record=ps,
            job=self,
            sync=self.sync,
        )
        self.source_adapter.load()

    def load_target_adapter(self) -> None:
        """Build the Nautobot-side adapter."""
        # FreePBX adapter doesn't yet populate Lines / SpeedDials / etc.,
        # so we exclude those button models from the diff to avoid
        # orphan-deleting any populated by other phone systems on the
        # same Nautobot instance.
        self.target_adapter = PhonesNautobotAdapter(
            job=self,
            sync=self.sync,
            include_lines=False,
        )
        self.target_adapter.load()


jobs = [FreePBXDataSource]
register_jobs(*jobs)
