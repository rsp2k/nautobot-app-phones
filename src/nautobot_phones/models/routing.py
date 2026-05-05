"""Routing: Trunk, RouteList, RouteGroup, RoutePattern.

Trunks are the egress paths from the call agent. RouteLists wrap RouteGroups
in priority order; RouteGroups wrap egress devices (Trunks, AnalogGateways)
with a member-selection algorithm. RoutePatterns match dialed digits and
choose where to send the call — out a Trunk, into a translation DN, or
through a RouteList to whichever group/device the algorithm picks.

The RoutePattern target is XOR across three options enforced by a CHECK
constraint: exactly one of (target_trunk, target_dn, target_route_list).
"""

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from nautobot.apps.models import BaseModel, PrimaryModel

from nautobot_phones.choices import RouteGroupAlgorithmChoices, TrunkTypeChoices


class Trunk(PrimaryModel):
    """An egress path from the phone system (SIP, PRI, H.323, MGCP)."""

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="trunks",
    )
    trunk_type = models.CharField(
        max_length=16,
        choices=TrunkTypeChoices,
    )
    destination_address = models.CharField(
        max_length=255,
        blank=True,
        help_text="FQDN or IP of the trunk far end (SIP). Blank for PRI/MGCP physical trunks.",
    )
    destination_port = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Far-end port (typically 5060 for SIP).",
    )
    css = models.ForeignKey(
        to="nautobot_phones.CallingSearchSpace",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outbound_trunks",
        verbose_name="CSS",
        help_text="CSS used for outbound calls leaving via this trunk.",
    )
    inbound_css = models.ForeignKey(
        to="nautobot_phones.CallingSearchSpace",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inbound_trunks",
        verbose_name="Inbound CSS",
        help_text="CSS applied to inbound calls arriving on this trunk.",
    )
    vendor_extras = models.JSONField(default=dict, blank=True)

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for Trunk."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class RouteList(PrimaryModel):
    """A CCM Route List — an ordered collection of RouteGroups.

    Route patterns target a RouteList, which evaluates its member groups
    in priority order. The first group with an available device handles
    the call.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="route_lists",
    )
    description = models.TextField(blank=True)
    vendor_extras = models.JSONField(default=dict, blank=True)

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for RouteList."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class RouteGroup(PrimaryModel):
    """A CCM Route Group — set of egress devices (Trunks, AnalogGateways).

    Members are evaluated by `distribution_algorithm`: top-down picks the
    first available member at each call; circular round-robins across
    members. Route Lists reference RouteGroups in priority order.
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="route_groups",
    )
    description = models.TextField(blank=True)
    distribution_algorithm = models.CharField(
        max_length=16,
        choices=RouteGroupAlgorithmChoices,
        default=RouteGroupAlgorithmChoices.TOP_DOWN,
    )
    vendor_extras = models.JSONField(default=dict, blank=True)

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for RouteGroup."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class RouteListMember(BaseModel):
    """Through-table — which RouteGroups belong to a RouteList, in priority order."""

    route_list = models.ForeignKey(
        to="nautobot_phones.RouteList",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    route_group = models.ForeignKey(
        to="nautobot_phones.RouteGroup",
        on_delete=models.PROTECT,
        related_name="route_list_memberships",
    )
    priority = models.PositiveIntegerField(
        help_text="Lower number = evaluated first.",
    )

    class Meta:
        """Meta options for RouteListMember."""

        ordering = ("route_list", "priority")
        unique_together = (
            ("route_list", "route_group"),
            ("route_list", "priority"),
        )
        verbose_name = "route list member"
        verbose_name_plural = "route list members"

    def __str__(self) -> str:
        """Display string."""
        return f"{self.route_list.name}[{self.priority}] -> {self.route_group.name}"


class RouteGroupMember(BaseModel):
    """Through-table — which devices belong to a RouteGroup.

    Uses GenericForeignKey so a Route Group can contain Trunks AND
    AnalogGateways (and future device types) without per-target FK
    columns. limit_choices_to keeps the UI dropdown sensible.
    """

    route_group = models.ForeignKey(
        to="nautobot_phones.RouteGroup",
        on_delete=models.CASCADE,
        related_name="members",
    )
    target_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        limit_choices_to=models.Q(app_label="nautobot_phones") & (
            models.Q(model="trunk") | models.Q(model="analoggateway")
        ),
    )
    target_id = models.UUIDField()
    target = GenericForeignKey("target_type", "target_id")
    priority = models.PositiveIntegerField(
        help_text="Lower number = evaluated first within the algorithm.",
    )

    class Meta:
        """Meta options for RouteGroupMember."""

        ordering = ("route_group", "priority")
        verbose_name = "route group member"
        verbose_name_plural = "route group members"
        indexes = [
            models.Index(fields=["target_type", "target_id"]),
        ]

    def __str__(self) -> str:
        """Display string."""
        return f"{self.route_group.name}[{self.priority}] -> {self.target}"


class RoutePattern(PrimaryModel):
    """A digit-matching pattern that routes to a Trunk, RouteList, or DN.

    CCM patterns support wildcards like '9.[2-9]XX[2-9]XXXXXX'. Each pattern
    targets exactly one of:
      - target_trunk: "send out this trunk" directly (rare in CCM —
        usually goes through a route list)
      - target_route_list: "evaluate this route list" (common)
      - target_dn: "translate to this DN" (translation pattern)

    The CHECK constraint enforces XOR across all three. DB-level so a
    misbehaving adapter can't sneak two-of-three in.
    """

    pattern = models.CharField(
        max_length=100,
        help_text="Digit pattern (e.g. '9.[2-9]XX[2-9]XXXXXX', '+15551234XXX').",
    )
    partition = models.ForeignKey(
        to="nautobot_phones.Partition",
        on_delete=models.PROTECT,
        related_name="route_patterns",
    )
    css = models.ForeignKey(
        to="nautobot_phones.CallingSearchSpace",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="route_patterns",
        verbose_name="CSS",
        help_text="CSS applied to the leg generated by this match (intra-cluster routing).",
    )
    target_trunk = models.ForeignKey(
        to="nautobot_phones.Trunk",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="route_patterns",
    )
    target_route_list = models.ForeignKey(
        to="nautobot_phones.RouteList",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="route_patterns",
    )
    target_dn = models.ForeignKey(
        to="nautobot_phones.DirectoryNumber",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="translation_patterns",
        help_text="If set, this pattern translates incoming digits to this DN.",
    )
    urgent = models.BooleanField(
        default=False,
        help_text="If true, dial as soon as the pattern matches (no inter-digit timeout).",
    )
    discard_digits = models.CharField(
        max_length=64,
        blank=True,
        help_text="Vendor-specific digit-discard rule (e.g. 'PreDot').",
    )

    natural_key_field_names = ["partition", "pattern"]

    class Meta:
        """Meta options for RoutePattern."""

        ordering = ("partition", "pattern")
        unique_together = (("partition", "pattern"),)
        constraints = [
            models.CheckConstraint(
                # Exactly one of (target_trunk, target_route_list, target_dn) must be set.
                check=(
                    models.Q(target_trunk__isnull=False, target_route_list__isnull=True, target_dn__isnull=True)
                    | models.Q(target_trunk__isnull=True, target_route_list__isnull=False, target_dn__isnull=True)
                    | models.Q(target_trunk__isnull=True, target_route_list__isnull=True, target_dn__isnull=False)
                ),
                name="route_pattern_exactly_one_target",
            ),
        ]

    def __str__(self) -> str:
        """Display string."""
        return f"{self.partition.name}/{self.pattern}"
