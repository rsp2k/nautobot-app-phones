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
    circuit = models.ForeignKey(
        to="circuits.Circuit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="phone_trunks",
        help_text="Optional: the carrier circuit this PBX-side trunk terminates. "
                  "Multiple Trunks (e.g. active/standby SBC pair) may point at "
                  "the same Circuit.",
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
    """An ordered priority list of RouteGroups (vendor-agnostic).

    Route patterns target a RouteList, which evaluates its member groups
    in priority order — the first group with an available device handles
    the call. Maps to CCM's Route List; FreePBX outbound-route priorities
    follow the same shape.
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


class TranslationPattern(PrimaryModel):
    """A digit-translation pattern applied before route-pattern matching.

    Matches a dialed number, applies digit transformations (prefix/strip/
    mask), and re-routes the call through the dial plan. Distinct from
    RoutePattern — translation patterns don't have a direct destination,
    they REWRITE digits and let the dial plan re-evaluate them.

    Vendor-agnostic concept: maps to CCM's TransPattern, FreePBX dialplan
    rewrite rules, Asterisk dialplan logic. Field grouping mirrors CCM's
    admin form (Pattern Definition / Calling Party / Called Party
    Transformations) since that's the most common operator workflow.
    Long-tail vendor-specific dropdowns live in `vendor_extras`.
    """

    # ---- Pattern Definition --------------------------------------------------
    pattern = models.CharField(
        max_length=100,
        help_text="Dial pattern to match (CCM wildcards: X, [n-m], !, .).",
    )
    partition = models.ForeignKey(
        to="nautobot_phones.Partition",
        on_delete=models.PROTECT,
        related_name="translation_patterns",
    )
    css = models.ForeignKey(
        to="nautobot_phones.CallingSearchSpace",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="translation_patterns",
        verbose_name="CSS",
        help_text="CSS used when re-evaluating the translated digits.",
    )
    description = models.CharField(max_length=200, blank=True)
    block_enable = models.BooleanField(
        default=False,
        help_text="If true, this pattern BLOCKS the call rather than translating it.",
    )
    release_clause = models.CharField(
        max_length=64, blank=True, default="",
        help_text='Block reason (e.g. "No Error", "Unallocated Number"). '
                  "Only meaningful when block_enable=True.",
    )
    urgent_priority = models.BooleanField(
        default=False,
        help_text="Match this pattern as soon as it qualifies — don't wait for inter-digit timeout.",
    )
    provide_outside_dial_tone = models.BooleanField(default=False)
    use_originator_css = models.BooleanField(
        default=False,
        help_text="If true, re-evaluation uses the originating phone's CSS rather than this pattern's CSS.",
    )
    dont_wait_for_idt = models.BooleanField(
        default=False, verbose_name="Don't Wait for IDT",
        help_text="Do not wait for interdigit timeout on subsequent dial-plan hops.",
    )
    route_next_hop_by_cgpn = models.BooleanField(
        default=False, verbose_name="Route Next Hop by Calling Party",
    )
    is_emergency_service_number = models.BooleanField(default=False)
    route_class = models.CharField(max_length=32, blank=True, default="Default")

    # ---- Calling Party Transformations ---------------------------------------
    use_calling_party_phone_mask = models.CharField(
        max_length=16, blank=True, default="Off",
        help_text='Tri-state: "Off", "On", or "Default".',
    )
    calling_party_transformation_mask = models.CharField(max_length=64, blank=True)
    calling_party_prefix_digits = models.CharField(max_length=64, blank=True)

    # ---- Called Party Transformations ----------------------------------------
    digit_discard_instruction = models.CharField(
        max_length=64, blank=True,
        help_text='Named DDI applied to dialed digits (e.g. "PreDot", "PreAt").',
    )
    called_party_transformation_mask = models.CharField(max_length=64, blank=True)
    prefix_digits_out = models.CharField(
        max_length=64, blank=True,
        help_text="Digits prepended to the called number (CCM 'Prefix Digits (Outgoing Calls)').",
    )

    # ---- Vendor extras -------------------------------------------------------
    vendor_extras = models.JSONField(
        default=dict, blank=True,
        help_text="Long-tail CCM fields (presentation bits, numbering plans, etc.).",
    )

    natural_key_field_names = ["partition", "pattern"]

    class Meta:
        """Meta options for TranslationPattern."""

        ordering = ("partition", "pattern")
        unique_together = (("partition", "pattern"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.partition.name}/{self.pattern}"


# --------------------------------------------------------------------------
# Hunt subsystem — multi-phone ring-group call routing
# --------------------------------------------------------------------------
#
# CCM call flow when someone dials a hunt pattern:
#
#   Dialed digits → HuntPilot (matches like a RoutePattern)
#                 → HuntList (ordered priority list of LineGroups)
#                 → LineGroup (distribution algorithm over a list of DNs)
#                 → DN(s) ring per the algorithm (top-down, circular,
#                   broadcast, or longest-idle)
#
# When all DNs in all LineGroups are exhausted without an answer, the
# HuntPilot's forward_hunt_no_answer destination kicks in. Same for busy.
#
# Same through-table pattern as RouteList → RouteGroup → trunks; the
# hunt subsystem just terminates at DNs (real people's phones) rather
# than trunks (call-routing destinations).


class HuntList(PrimaryModel):
    """A priority-ordered list of LineGroups.

    Wraps the 'when this hunt fires, here's the ordered list of
    LineGroups to try' configuration. Each LineGroup gets a chance to
    answer (per its own distribution algorithm); if nothing in the
    LineGroup answers, the next LineGroup in the HuntList is tried.

    HuntList → LineGroup is the M2M through HuntListMember (selection_order).
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="hunt_lists",
    )
    description = models.CharField(max_length=200, blank=True)
    route_list_enabled = models.BooleanField(default=True)
    voice_mail_usage = models.BooleanField(default=False)
    # CCM-specific concepts (callManagerGroupName etc.) live here.
    vendor_extras = models.JSONField(default=dict, blank=True)
    line_groups = models.ManyToManyField(
        to="nautobot_phones.LineGroup",
        through="nautobot_phones.HuntListMember",
        related_name="hunt_lists",
        blank=True,
    )

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for HuntList."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class LineGroup(PrimaryModel):
    """A group of DNs with a distribution algorithm.

    LineGroups are the leaf objects of the hunt subsystem — they hold
    the actual list of phones (via DN refs) that ring when the hunt
    fires. The distribution_algorithm determines whether all ring at
    once (broadcast), one at a time in order (top-down), or in rotation
    (circular / longest-idle).

    LineGroup → DirectoryNumber is the M2M through LineGroupMember
    (line_selection_order).
    """

    name = models.CharField(max_length=100)
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="line_groups",
    )
    distribution_algorithm = models.CharField(
        max_length=32, blank=True,
        help_text='"Top Down", "Circular", "Broadcast", or "Longest Idle Time".',
    )
    rna_reversion_timeout = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="RNA Reversion Timeout (sec)",
        help_text="Seconds before Ring-No-Answer triggers algorithm advance.",
    )
    hunt_algorithm_no_answer = models.CharField(
        max_length=100, blank=True,
        help_text='What to do when this group runs out of phones to ring without answer.',
    )
    hunt_algorithm_busy = models.CharField(
        max_length=100, blank=True,
        help_text='What to do when all phones in this group are busy.',
    )
    hunt_algorithm_not_available = models.CharField(
        max_length=100, blank=True,
        help_text='What to do when no phones in this group are reachable.',
    )
    auto_log_off_hunt = models.BooleanField(default=False)
    vendor_extras = models.JSONField(default=dict, blank=True)
    directory_numbers = models.ManyToManyField(
        to="nautobot_phones.DirectoryNumber",
        through="nautobot_phones.LineGroupMember",
        related_name="line_groups",
        blank=True,
    )

    natural_key_field_names = ["phone_system", "name"]

    class Meta:
        """Meta options for LineGroup."""

        ordering = ("phone_system", "name")
        unique_together = (("phone_system", "name"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone_system.name}/{self.name}"


class HuntListMember(BaseModel):
    """Through-table for HuntList → LineGroup with selection order."""

    hunt_list = models.ForeignKey(
        to="nautobot_phones.HuntList",
        on_delete=models.CASCADE,
        related_name="members",
    )
    line_group = models.ForeignKey(
        to="nautobot_phones.LineGroup",
        on_delete=models.PROTECT,
        related_name="hunt_list_memberships",
    )
    selection_order = models.PositiveSmallIntegerField(
        help_text="1-based priority — lower order tries first.",
    )

    class Meta:
        """Meta options for HuntListMember."""

        ordering = ("hunt_list", "selection_order")
        unique_together = (("hunt_list", "line_group"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.hunt_list.name}[{self.selection_order}] -> {self.line_group.name}"


class LineGroupMember(BaseModel):
    """Through-table for LineGroup → DirectoryNumber with line selection order."""

    line_group = models.ForeignKey(
        to="nautobot_phones.LineGroup",
        on_delete=models.CASCADE,
        related_name="members",
    )
    directory_number = models.ForeignKey(
        to="nautobot_phones.DirectoryNumber",
        on_delete=models.PROTECT,
        related_name="line_group_memberships",
    )
    line_selection_order = models.PositiveSmallIntegerField(
        help_text="0-based priority within the group.",
    )

    class Meta:
        """Meta options for LineGroupMember."""

        ordering = ("line_group", "line_selection_order")
        unique_together = (("line_group", "directory_number"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.line_group.name}[{self.line_selection_order}] -> {self.directory_number.extension}"


class HuntPilot(PrimaryModel):
    """A dial pattern that triggers hunt-list distribution.

    Like RoutePattern but the destination is always a HuntList (not a
    trunk or single DN). Hunt-specific overflow fields capture what
    happens when the hunt fails: `forward_hunt_no_answer_destination`
    and `forward_hunt_busy_destination` are call-forward targets when
    the hunt list is exhausted.
    """

    pattern = models.CharField(max_length=100)
    partition = models.ForeignKey(
        to="nautobot_phones.Partition",
        on_delete=models.PROTECT,
        related_name="hunt_pilots",
    )
    description = models.CharField(max_length=200, blank=True)
    hunt_list = models.ForeignKey(
        to="nautobot_phones.HuntList",
        on_delete=models.PROTECT,
        related_name="hunt_pilots",
        null=True, blank=True,
        help_text="The HuntList that receives matching calls.",
    )
    alerting_name = models.CharField(
        max_length=64, blank=True,
        help_text="Display name shown on ringing phones.",
    )
    max_hunt_duration = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Max Hunt Duration (sec)",
        help_text="Total time the hunt may run before forwarding to no-answer destination.",
    )
    forward_hunt_no_answer_destination = models.CharField(
        max_length=64, blank=True,
        help_text="Where to send the call when the hunt list is exhausted without answer.",
    )
    forward_hunt_busy_destination = models.CharField(
        max_length=64, blank=True,
        help_text="Where to send the call when all phones in the hunt are busy.",
    )
    vendor_extras = models.JSONField(default=dict, blank=True)

    natural_key_field_names = ["partition", "pattern"]

    class Meta:
        """Meta options for HuntPilot."""

        ordering = ("partition", "pattern")
        unique_together = (("partition", "pattern"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.partition.name}/{self.pattern}"
