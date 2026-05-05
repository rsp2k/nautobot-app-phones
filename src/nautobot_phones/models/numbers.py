"""Numbers and assignments: Carrier, DirectoryNumber, DIDBlock, DID, DIDAssignment.

DID modeling uses ranges (DIDBlock) as primary records. Individual DID rows
materialize only when an individual number gets assigned or marked special
(reserved, test, fax-only, etc.).
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from nautobot.apps.models import BaseModel, OrganizationalModel, PrimaryModel


class Carrier(OrganizationalModel):
    """A telecom carrier providing DIDs and trunks (Verizon, AT&T, Twilio, etc.)."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    account_number = models.CharField(
        max_length=64,
        blank=True,
        help_text="Carrier-side account or BAN identifier (informational).",
    )

    natural_key_field_names = ["name"]

    class Meta:
        """Meta options for Carrier."""

        ordering = ("name",)

    def __str__(self) -> str:
        """Display string."""
        return self.name


class DirectoryNumber(PrimaryModel):
    """A directory number (extension) within a Partition.

    In CCM, a "Line" object IS a DN. We use the name DirectoryNumber to avoid
    clashing with our own Line model (the phone-button appearance). DNs live
    in a Partition; phones reach them via their CallingSearchSpace.
    """

    extension = models.CharField(
        max_length=32,
        help_text="Internal extension or full E.164 (e.g. '4825', '+15551234825').",
    )
    partition = models.ForeignKey(
        to="nautobot_phones.Partition",
        on_delete=models.PROTECT,
        related_name="directory_numbers",
    )
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="directory_numbers",
        help_text="Denormalized — equals partition.phone_system. Indexed for query speed.",
    )
    alerting_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name shown on the called party's display (e.g. 'Alice — Sales').",
    )
    voicemail_profile = models.CharField(
        max_length=100,
        blank=True,
        help_text="Vendor-specific voicemail profile name (free-form).",
    )
    vendor_extras = models.JSONField(
        default=dict,
        blank=True,
        help_text="Vendor-specific fields not modeled as columns. Adapter-driven.",
    )

    natural_key_field_names = ["partition", "extension"]

    class Meta:
        """Meta options for DirectoryNumber."""

        ordering = ("partition", "extension")
        unique_together = (("partition", "extension"),)
        verbose_name = "directory number"
        verbose_name_plural = "directory numbers"

    def clean_fields(self, exclude=None) -> None:
        """Auto-populate the denormalized phone_system FK from partition.

        Must run before super().clean_fields() because that's where the
        null=False validator on phone_system fires. The field is
        denormalized for query speed but always equals
        partition.phone_system, so callers only need to set partition.
        """
        if self.partition_id and not self.phone_system_id:
            self.phone_system_id = self.partition.phone_system_id
        super().clean_fields(exclude=exclude)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.partition.name}/{self.extension}"


class DIDBlock(PrimaryModel):
    """A contiguous block of DIDs from a carrier.

    The primary unit of DID inventory. Individual DIDs only get materialized
    as DID rows when assigned (to a DN, trunk, voicemail) or marked special.
    Membership query: a number `n` belongs to this block iff
    start_e164 <= n <= end_e164 (lexicographic, given equal-length zero-padded strings).
    """

    start_e164 = models.CharField(
        max_length=32,
        help_text="First number in the block, digits only, zero-padded to a fixed length.",
    )
    end_e164 = models.CharField(
        max_length=32,
        help_text="Last number in the block, digits only, same length as start_e164.",
    )
    carrier = models.ForeignKey(
        to="nautobot_phones.Carrier",
        on_delete=models.PROTECT,
        related_name="did_blocks",
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Site the block is delivered to (informational).",
    )
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="did_blocks",
        help_text="Phone system this block routes to (optional — may be unassigned).",
    )
    description = models.TextField(blank=True)

    class Meta:
        """Meta options for DIDBlock."""

        ordering = ("carrier", "start_e164")
        unique_together = (("start_e164", "end_e164", "carrier"),)
        verbose_name = "DID block"
        verbose_name_plural = "DID blocks"

    def clean(self) -> None:
        """Validate E.164 format and range ordering.

        Lexicographic comparison only works correctly when both strings are
        the same length and digits-only — so enforce both.
        """
        super().clean()
        if not self.start_e164.isdigit():
            raise ValidationError({"start_e164": "Must be digits only (no '+', spaces, or dashes)."})
        if not self.end_e164.isdigit():
            raise ValidationError({"end_e164": "Must be digits only (no '+', spaces, or dashes)."})
        if len(self.start_e164) != len(self.end_e164):
            raise ValidationError(
                "start_e164 and end_e164 must be the same length (zero-pad shorter values)."
            )
        if self.start_e164 > self.end_e164:
            raise ValidationError("start_e164 must be <= end_e164.")

    @property
    def size(self) -> int:
        """Count of numbers in the block (inclusive)."""
        return int(self.end_e164) - int(self.start_e164) + 1

    def __str__(self) -> str:
        """Display string."""
        return f"{self.start_e164}-{self.end_e164} ({self.carrier.name})"


class DID(PrimaryModel):
    """An individual DID number, materialized when assigned or marked special."""

    e164 = models.CharField(max_length=32, unique=True)
    block = models.ForeignKey(
        to="nautobot_phones.DIDBlock",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dids",
        help_text="Parent block. Null for one-off DIDs not part of any block.",
    )
    is_special = models.BooleanField(
        default=False,
        help_text="Reserved, test, or otherwise non-routable (e.g. number-test ranges).",
    )

    natural_key_field_names = ["e164"]

    class Meta:
        """Meta options for DID."""

        ordering = ("e164",)
        verbose_name = "DID"
        verbose_name_plural = "DIDs"

    def __str__(self) -> str:
        """Display string."""
        return self.e164


class DIDAssignment(BaseModel):
    """Maps a DID to whatever it routes to (DN, Trunk, or future Voicemail).

    GenericForeignKey lets a single assignment table hold heterogeneous
    targets without per-target FK columns. Filtering: `target_type` is
    constrained to the small set of valid model types via `limit_choices_to`.
    """

    did = models.OneToOneField(
        to="nautobot_phones.DID",
        on_delete=models.CASCADE,
        related_name="assignment",
    )
    target_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        limit_choices_to=models.Q(app_label="nautobot_phones") & (
            models.Q(model="directorynumber") | models.Q(model="trunk")
        ),
    )
    target_id = models.UUIDField()
    target = GenericForeignKey("target_type", "target_id")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for DIDAssignment."""

        ordering = ("-assigned_at",)
        verbose_name = "DID assignment"
        verbose_name_plural = "DID assignments"
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        """Display string."""
        return f"{self.did.e164} -> {self.target}"
