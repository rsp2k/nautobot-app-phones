"""Analog media gateways and their FXS/FXO ports.

Distinct from Phone because gateways aren't endpoints — they're media
gateways with N analog ports. An ATA, by contrast, IS modeled as a Phone
since it registers as an endpoint with line buttons.
"""

from django.db import models
from nautobot.apps.models import BaseModel, PrimaryModel

from nautobot_phones.choices import AnalogGatewayProtocolChoices, AnalogPortTypeChoices


class AnalogGateway(PrimaryModel):
    """An analog media gateway (Cisco VG-series, Sangoma Vega, Patton, etc.).

    Multi-port device that bridges analog phones (FXS) or analog lines (FXO)
    to the IP-based call agent.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="analog_gateways",
    )
    location = models.ForeignKey(
        to="dcim.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional link to a Nautobot Device record.",
    )
    model = models.CharField(
        max_length=64,
        blank=True,
        help_text="Gateway model string (e.g. 'VG350', 'Vega-50-FXS').",
    )
    protocol = models.CharField(
        max_length=16,
        choices=AnalogGatewayProtocolChoices,
        help_text="Control protocol the gateway speaks toward the call agent.",
    )
    vendor_extras = models.JSONField(default=dict, blank=True)

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for AnalogGateway."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)
        verbose_name = "analog gateway"
        verbose_name_plural = "analog gateways"

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class AnalogPort(BaseModel):
    """A single analog port on a gateway.

    FXS ports connect to analog phones (and carry a DN); FXO ports connect to
    PSTN lines from the carrier (no DN, since they're inbound).
    """

    gateway = models.ForeignKey(
        to="nautobot_phones.AnalogGateway",
        on_delete=models.CASCADE,
        related_name="ports",
    )
    port_index = models.PositiveSmallIntegerField(
        help_text="1-based port number on the gateway face.",
    )
    port_type = models.CharField(
        max_length=8,
        choices=AnalogPortTypeChoices,
    )
    directory_number = models.ForeignKey(
        to="nautobot_phones.DirectoryNumber",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analog_ports",
        help_text="Only set for FXS ports (FXO ports terminate carrier lines).",
    )

    class Meta:
        """Meta options for AnalogPort."""

        ordering = ("gateway", "port_index")
        unique_together = (("gateway", "port_index"),)
        verbose_name = "analog port"
        verbose_name_plural = "analog ports"

    def __str__(self) -> str:
        """Display string."""
        return f"{self.gateway.name}[{self.port_index}] ({self.port_type})"
