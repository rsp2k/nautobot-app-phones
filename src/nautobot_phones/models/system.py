"""PhoneSystem model — the cluster/system root.

Every other record in this app belongs (directly or transitively) to a
PhoneSystem: phones, directory numbers, trunks, partitions, route patterns.
Sync jobs operate on one PhoneSystem at a time.
"""

from django.db import models
from nautobot.apps.models import PrimaryModel

from nautobot_phones.choices import VendorChoices


class PhoneSystem(PrimaryModel):
    """A phone-system instance — a CCM cluster, FreePBX server, or Asterisk box.

    Holds connection metadata (hostname, secrets) and per-instance sync
    policy. Read-only mirror semantics: the live system is authoritative,
    Nautobot reflects state.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable identifier (e.g. 'NYC-CCM-PUB', 'BRANCH-FPX-01').",
    )
    vendor = models.CharField(
        max_length=32,
        choices=VendorChoices,
        help_text="Phone-system vendor / flavor.",
    )
    version = models.CharField(
        max_length=64,
        blank=True,
        help_text="Vendor version string (e.g. '15.0.1.12900-234' for CCM).",
    )
    hostname = models.CharField(
        max_length=255,
        blank=True,
        help_text="FQDN or IP of the management endpoint (CCM publisher, FreePBX server).",
    )
    secrets_group = models.ForeignKey(
        to="extras.SecretsGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="SecretsGroup carrying credentials for the management API.",
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Primary site for the system (informational; phones may live elsewhere).",
    )
    delete_policy = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-model delete behavior on sync. Map of model name to action "
            "('delete', 'ignore', 'flag'). Example: "
            "{'phone': 'flag', 'did': 'delete', 'trunk': 'ignore'}. "
            "Models not listed default to 'flag'."
        ),
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last successful sync run against this system.",
    )

    natural_key_field_names = ["name"]

    class Meta:
        """Meta options for PhoneSystem."""

        ordering = ("name",)
        verbose_name = "phone system"
        verbose_name_plural = "phone systems"

    def __str__(self) -> str:
        """Display string."""
        return self.name
