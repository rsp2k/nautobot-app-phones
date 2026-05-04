"""Endpoint models: Phone (including ATAs as a model variant) and Line.

A Phone is any registered endpoint device — desk phone, softphone, ATA. A
Line is a single button/appearance on a phone, mapping that button to a
DirectoryNumber.
"""

from django.db import models
from nautobot.apps.models import BaseModel, MACAddressCharField, PrimaryModel

from nautobot_phones.choices import RegistrationStatusChoices


class Phone(PrimaryModel):
    """A registered phone endpoint.

    Handles both regular IP phones (Cisco 8861, Yealink T54W, etc.) and ATAs
    (Cisco ATA-191, Grandstream HT-series). An ATA is just a Phone whose
    `model` indicates it's an ATA — its FXS ports appear as Line rows.
    """

    device_name = models.CharField(
        max_length=100,
        help_text="Vendor-side device name (e.g. 'SEP001122334455' on CCM).",
    )
    mac_address = MACAddressCharField(
        help_text="Device MAC. Required by CCM; usually set on FreePBX devices too.",
    )
    model = models.CharField(
        max_length=64,
        blank=True,
        help_text="Phone model string (e.g. 'CP-8851', 'ATA-191', 'T54W').",
    )
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="phones",
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Where the phone physically lives.",
    )
    device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional link to a Nautobot Device record (for cable/port mapping).",
    )
    registration_status = models.CharField(
        max_length=32,
        choices=RegistrationStatusChoices,
        default=RegistrationStatusChoices.UNKNOWN,
    )
    vendor_extras = models.JSONField(
        default=dict,
        blank=True,
        help_text="Vendor-specific fields not modeled as columns.",
    )

    natural_key_field_names = ["phone_system", "mac_address"]

    class Meta:
        """Meta options for Phone."""

        ordering = ("phone_system", "device_name")
        unique_together = (("phone_system", "mac_address"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.device_name} ({self.mac_address})"


class Line(BaseModel):
    """A single line/button appearance on a phone.

    Cisco phones have N line buttons; each can hold a DN with display label,
    ring setting, etc. Pure junction model — no list/detail views of its own,
    so we use BaseModel rather than PrimaryModel.
    """

    phone = models.ForeignKey(
        to="nautobot_phones.Phone",
        on_delete=models.CASCADE,
        related_name="lines",
    )
    directory_number = models.ForeignKey(
        to="nautobot_phones.DirectoryNumber",
        on_delete=models.PROTECT,
        related_name="lines",
    )
    button_index = models.PositiveSmallIntegerField(
        help_text="1-based position of this line button on the phone.",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Short label shown next to the button (e.g. 'Sales').",
    )
    display = models.CharField(
        max_length=100,
        blank=True,
        help_text="Internal display text (vendor-specific).",
    )
    ring_setting = models.CharField(
        max_length=32,
        blank=True,
        help_text="Ring behavior (e.g. 'Ring', 'Beep', 'Silent', 'Disable').",
    )

    class Meta:
        """Meta options for Line."""

        ordering = ("phone", "button_index")
        unique_together = (("phone", "button_index"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone.device_name}[{self.button_index}] -> {self.directory_number.extension}"
