"""Vendor-agnostic phone-system feature config: DeviceProfile, CallPickupGroup, VoicemailProfile.

These are the "shared configuration objects" that endpoints (phones, DNs)
reference by name. They're modeled vendor-agnostically — CCM-specific
concepts like Region/Location/CallManagerGroup/SRSTReference don't get
their own tables; they live in `DeviceProfile.vendor_extras` so a FreePBX
adapter or any other vendor can populate this graph without us schema-
migrating around their differences.

Mapping at a glance:

| This app | Cisco UCM | FreePBX |
|----------|-----------|---------|
| `DeviceProfile` | DevicePool | (device template / device base config) |
| `CallPickupGroup` | CallPickupGroup | Call Pickup Groups |
| `VoicemailProfile` | VoiceMailProfile | (voicemail box / vmail config) |
"""

from django.db import models
from nautobot.apps.models import BaseModel, PrimaryModel


class DeviceProfile(PrimaryModel):
    """A named bundle of device-level config defaults (vendor-agnostic).

    On Cisco this maps to a DevicePool — a record that bundles up CCM-
    specific settings (CallManagerGroup, Region, Location, DateTimeGroup,
    SRSTReference, MediaResourceList, etc.) and applies them to whichever
    phones reference it. On FreePBX this maps to a device template /
    base-config record.

    The CCM-specific ancillary names (region, location, etc.) live in
    `vendor_extras` rather than being promoted to their own first-class
    models, because those concepts are perpetually NULL for vendors
    that don't have call-admission-control bandwidth zones.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="device_profiles",
    )
    description = models.CharField(max_length=200, blank=True)
    vendor_extras = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Vendor-specific bundled config values. For Cisco UCM, contains "
            "callManagerGroupName, regionName, locationName, dateTimeSettingName, "
            "srstName, mediaResourceListName, networkLocale, etc."
        ),
    )

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for DeviceProfile."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)
        verbose_name = "device profile"
        verbose_name_plural = "device profiles"


class VoicemailProfile(PrimaryModel):
    """A named voicemail box/config record (vendor-agnostic).

    On Cisco this maps to a VoiceMailProfile and references a "voice mail
    pilot" DN (typically the unity connection greeting line). On FreePBX
    this corresponds to per-extension voicemail box config — the model
    is generic enough that an adapter can synthesize one record per
    voicemail-enabled extension if needed.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="voicemail_profiles",
    )
    description = models.CharField(max_length=200, blank=True)
    pilot_dn = models.CharField(
        max_length=50, blank=True,
        verbose_name="Pilot DN",
        help_text="DN dialed to reach the voicemail system (e.g. 'Unity Connection' line).",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this profile is the cluster default for newly-created DNs.",
    )
    vendor_extras = models.JSONField(default=dict, blank=True)

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for VoicemailProfile."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)
        verbose_name = "voicemail profile"
        verbose_name_plural = "voicemail profiles"


class CallPickupGroup(PrimaryModel):
    """A call-pickup group — a dialed pattern that picks up ringing peers.

    Vendor-agnostic: both Cisco UCM and FreePBX have this concept with
    the same shape. An extension dials the group's pickup pattern (e.g.
    `*8` or `1206`) and the system answers whichever member-DN is
    currently ringing. Members are DirectoryNumber records, joined
    through `CallPickupGroupMember` with a priority/ordering field.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="call_pickup_groups",
    )
    pattern = models.CharField(
        max_length=50,
        help_text="Extension/digits dialed to invoke pickup (e.g. '*8', '1206').",
    )
    partition = models.ForeignKey(
        to="nautobot_phones.Partition",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="call_pickup_groups",
    )
    description = models.CharField(max_length=200, blank=True)
    vendor_extras = models.JSONField(default=dict, blank=True)
    members = models.ManyToManyField(
        to="nautobot_phones.DirectoryNumber",
        through="nautobot_phones.CallPickupGroupMember",
        related_name="call_pickup_groups",
        blank=True,
    )

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for CallPickupGroup."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)
        verbose_name = "call pickup group"
        verbose_name_plural = "call pickup groups"


class CallPickupGroupMember(BaseModel):
    """Through-table: which DNs participate in which pickup groups.

    `priority` controls answer order when multiple peers are ringing
    simultaneously — lower numbers ring-grab first.
    """

    pickup_group = models.ForeignKey(
        to="nautobot_phones.CallPickupGroup",
        on_delete=models.CASCADE,
        related_name="member_through",
    )
    directory_number = models.ForeignKey(
        to="nautobot_phones.DirectoryNumber",
        on_delete=models.CASCADE,
        related_name="pickup_group_through",
    )
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        """Meta options for CallPickupGroupMember."""

        ordering = ("pickup_group", "priority")
        unique_together = (("pickup_group", "directory_number"),)
