"""django-tables2 Table classes for nautobot-app-phones list views.

Each PrimaryModel/OrganizationalModel gets a Table that defines its column
layout for the list view. Conventions: leading ToggleColumn for bulk-action
checkbox, linked `name`/`extension`/`pattern` column for navigation,
trailing ButtonsColumn for edit/delete actions.

Junction-style records (Line, AnalogPort, CSSPartitionMembership,
DIDAssignment) don't have standalone list pages — they render nested in
their parent's detail view in Phase 2c.
"""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from nautobot_phones import models


class PhoneSystemTable(BaseTable):
    """List-view table for PhoneSystem."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    actions = ButtonsColumn(models.PhoneSystem)

    class Meta(BaseTable.Meta):
        model = models.PhoneSystem
        fields = ("pk", "name", "vendor", "version", "hostname", "location", "last_synced_at", "actions")
        default_columns = ("pk", "name", "vendor", "version", "hostname", "actions")


class CarrierTable(BaseTable):
    """List-view table for Carrier."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    actions = ButtonsColumn(models.Carrier)

    class Meta(BaseTable.Meta):
        model = models.Carrier
        fields = ("pk", "name", "account_number", "description", "actions")
        default_columns = ("pk", "name", "account_number", "actions")


class PartitionTable(BaseTable):
    """List-view table for Partition."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.Partition)

    class Meta(BaseTable.Meta):
        model = models.Partition
        fields = ("pk", "name", "phone_system", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "actions")


class CallingSearchSpaceTable(BaseTable):
    """List-view table for CallingSearchSpace."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.CallingSearchSpace)

    class Meta(BaseTable.Meta):
        model = models.CallingSearchSpace
        fields = ("pk", "name", "phone_system", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "actions")


class DirectoryNumberTable(BaseTable):
    """List-view table for DirectoryNumber."""

    pk = ToggleColumn()
    extension = tables.LinkColumn(verbose_name="Directory Number")
    partition = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.DirectoryNumber)

    class Meta(BaseTable.Meta):
        model = models.DirectoryNumber
        fields = ("pk", "extension", "partition", "phone_system", "alerting_name", "voicemail_profile", "actions")
        default_columns = ("pk", "extension", "partition", "phone_system", "alerting_name", "actions")


class DIDBlockTable(BaseTable):
    """List-view table for DIDBlock."""

    pk = ToggleColumn()
    start_e164 = tables.LinkColumn(verbose_name="Start")
    end_e164 = tables.Column(verbose_name="End")
    carrier = tables.LinkColumn()
    location = tables.LinkColumn()
    size = tables.Column(orderable=False)
    actions = ButtonsColumn(models.DIDBlock)

    class Meta(BaseTable.Meta):
        model = models.DIDBlock
        fields = ("pk", "start_e164", "end_e164", "size", "carrier", "location", "phone_system", "actions")
        default_columns = ("pk", "start_e164", "end_e164", "size", "carrier", "location", "actions")


class DIDTable(BaseTable):
    """List-view table for DID."""

    pk = ToggleColumn()
    e164 = tables.LinkColumn()
    block = tables.LinkColumn()
    is_special = tables.BooleanColumn()
    actions = ButtonsColumn(models.DID)

    class Meta(BaseTable.Meta):
        model = models.DID
        fields = ("pk", "e164", "block", "is_special", "actions")
        default_columns = ("pk", "e164", "block", "is_special", "actions")


class PhoneTable(BaseTable):
    """List-view table for Phone.

    `model` is a `@property` reading from `device.device_type.model`
    (Nautobot DCIM is the source of truth for hardware identity), so we
    expose it as a non-sortable accessor column rather than a sortable
    ORM field. Operators wanting to sort/filter by hardware should
    use the Devices list view directly.
    """

    pk = ToggleColumn()
    device_name = tables.LinkColumn()
    device_kind = tables.Column(verbose_name="Kind")
    mac_address = tables.Column()
    active_load = tables.Column(verbose_name="Running Load")
    # `model` and `physical_location` are @property accessors on Phone (read
    # through device.device_type.model and device.location). Non-sortable
    # since they're not real DB columns — operators wanting to sort/filter
    # by hardware should use the Devices list view directly.
    model = tables.Column(accessor="model", verbose_name="Model", orderable=False)
    physical_location = tables.Column(
        accessor="location", verbose_name="Physical Location", orderable=False,
    )
    phone_system = tables.LinkColumn()
    device_profile = tables.LinkColumn()
    media_zone = tables.Column(verbose_name="Media Zone")
    owner_user_id = tables.Column(verbose_name="Owner")
    actions = ButtonsColumn(models.Phone)

    class Meta(BaseTable.Meta):
        model = models.Phone
        fields = (
            "pk", "device_name", "device_kind", "mac_address", "model", "description",
            "phone_system", "physical_location", "media_zone",
            "device_profile", "owner_user_id",
            "registration_status", "last_registered_ip",
            "active_load", "inactive_load", "live_login_user",
            "actions",
        )
        default_columns = (
            "pk", "device_name", "device_kind", "description", "mac_address", "model",
            "phone_system", "media_zone", "device_profile",
            "last_registered_ip", "actions",
        )


class TrunkTable(BaseTable):
    """List-view table for Trunk."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    css = tables.LinkColumn(verbose_name="CSS")
    actions = ButtonsColumn(models.Trunk)

    class Meta(BaseTable.Meta):
        model = models.Trunk
        fields = ("pk", "name", "phone_system", "trunk_type", "destination_address", "destination_port", "css", "actions")
        default_columns = ("pk", "name", "phone_system", "trunk_type", "destination_address", "actions")


class RoutePatternTable(BaseTable):
    """List-view table for RoutePattern."""

    pk = ToggleColumn()
    pattern = tables.LinkColumn()
    partition = tables.LinkColumn()
    css = tables.LinkColumn(verbose_name="CSS")
    target_trunk = tables.LinkColumn()
    target_route_list = tables.LinkColumn(verbose_name="Target Route List")
    target_dn = tables.LinkColumn(verbose_name="Target DN")
    urgent = tables.BooleanColumn()
    actions = ButtonsColumn(models.RoutePattern)

    class Meta(BaseTable.Meta):
        model = models.RoutePattern
        fields = ("pk", "pattern", "partition", "css", "target_trunk", "target_route_list", "target_dn", "urgent", "discard_digits", "actions")
        default_columns = ("pk", "pattern", "partition", "target_trunk", "target_route_list", "target_dn", "urgent", "actions")


class RouteListTable(BaseTable):
    """List-view table for RouteList."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.RouteList)

    class Meta(BaseTable.Meta):
        model = models.RouteList
        fields = ("pk", "name", "phone_system", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "description", "actions")


class RouteGroupTable(BaseTable):
    """List-view table for RouteGroup."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.RouteGroup)

    class Meta(BaseTable.Meta):
        model = models.RouteGroup
        fields = ("pk", "name", "phone_system", "distribution_algorithm", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "distribution_algorithm", "actions")


class RouteListMemberTable(BaseTable):
    """Memberships embedded on RouteList detail (priority order)."""

    priority = tables.Column()
    route_group = tables.LinkColumn()
    route_list = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.RouteListMember
        fields = ("priority", "route_group", "route_list")
        default_columns = ("priority", "route_group")


class RouteGroupMemberTable(BaseTable):
    """Members embedded on RouteGroup detail."""

    priority = tables.Column()
    target_type = tables.Column(verbose_name="Target Type")
    route_group = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.RouteGroupMember
        fields = ("priority", "target_type", "route_group")
        default_columns = ("priority", "target_type")


class AnalogGatewayTable(BaseTable):
    """List-view table for AnalogGateway."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    location = tables.LinkColumn()
    actions = ButtonsColumn(models.AnalogGateway)

    class Meta(BaseTable.Meta):
        model = models.AnalogGateway
        fields = ("pk", "name", "phone_system", "location", "model", "protocol", "actions")
        default_columns = ("pk", "name", "phone_system", "location", "model", "protocol", "actions")


# --------------------------------------------------------------------------
# Junction-model tables — used in nested ObjectsTablePanel on parent details
# (e.g. "Lines on this phone", "Ports on this gateway"). These don't have
# standalone list URLs; they only render as embedded tables.
# --------------------------------------------------------------------------


class LineTable(BaseTable):
    """Lines (phone-button appearances) — embedded on Phone or DN detail.

    Default columns surface the "what does this button DO" essentials. Per-line
    enrichment (max calls, busy trigger, MWI policy, recording flag) shows up
    when configured but defaults to "—" when getPhone enrichment hasn't run.
    """

    button_index = tables.Column()
    phone = tables.LinkColumn()
    directory_number = tables.LinkColumn()
    max_num_calls = tables.Column(verbose_name="Max Calls")
    busy_trigger = tables.Column(verbose_name="Busy Trig")

    class Meta(BaseTable.Meta):
        model = models.Line
        fields = (
            "button_index", "phone", "directory_number", "label", "ring_setting",
            "max_num_calls", "busy_trigger",
        )
        default_columns = (
            "button_index", "phone", "directory_number", "label",
            "max_num_calls", "busy_trigger",
        )


class BusyLampFieldTable(BaseTable):
    """BLFs embedded on Phone detail."""

    button_index = tables.Column()
    destination = tables.Column()
    label = tables.Column()
    asterisk_service = tables.BooleanColumn(verbose_name="* Speed Dial")

    class Meta(BaseTable.Meta):
        model = models.BusyLampField
        fields = ("button_index", "destination", "label", "asterisk_service")
        default_columns = ("button_index", "destination", "label", "asterisk_service")


class AnalogPortTable(BaseTable):
    """Analog ports embedded on AnalogGateway or DN detail."""

    port_index = tables.Column()
    gateway = tables.LinkColumn()
    directory_number = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.AnalogPort
        fields = ("port_index", "gateway", "port_type", "directory_number")
        default_columns = ("port_index", "gateway", "port_type", "directory_number")


class TranslationPatternTable(BaseTable):
    """List-view table for TranslationPattern.

    Default columns surface the operationally-most-useful subset: pattern,
    partition, CSS, description, plus the called-party prefix
    (`prefix_digits_out`) which is the most-asked-about transform value
    when operators ask "what does this pattern actually DO?".
    """

    pk = ToggleColumn()
    pattern = tables.LinkColumn()
    partition = tables.LinkColumn()
    css = tables.LinkColumn()
    urgent_priority = tables.BooleanColumn(verbose_name="Urgent")
    block_enable = tables.BooleanColumn(verbose_name="Block")
    actions = ButtonsColumn(models.TranslationPattern)

    class Meta(BaseTable.Meta):
        model = models.TranslationPattern
        fields = (
            "pk", "pattern", "partition", "css", "description",
            "block_enable", "urgent_priority",
            "calling_party_transformation_mask", "calling_party_prefix_digits",
            "digit_discard_instruction", "called_party_transformation_mask",
            "prefix_digits_out",
            "actions",
        )
        default_columns = (
            "pk", "pattern", "partition", "css",
            "prefix_digits_out", "description", "actions",
        )


class SpeedDialTable(BaseTable):
    """Speed dials embedded on Phone detail."""

    button_index = tables.Column()
    number = tables.Column()
    label = tables.Column()

    class Meta(BaseTable.Meta):
        model = models.SpeedDial
        fields = ("button_index", "number", "label")
        default_columns = ("button_index", "number", "label")


class PhoneServiceUrlTable(BaseTable):
    """Service URL buttons embedded on Phone detail."""

    button_index = tables.Column()
    label = tables.Column()
    url = tables.Column()

    def render_url(self, value):
        """Wrap the URL in <a href> so it's clickable.

        CCM service URLs commonly include template variables like
        #DEVICENAME# / #EMCC# — those won't resolve as literal clicks
        but the wrapping is still useful for plain URLs and for
        copy-paste workflows.
        """
        from html import escape
        from django.utils.safestring import mark_safe
        return mark_safe(
            f'<a href="{escape(str(value))}" target="_blank" rel="noopener">{escape(str(value))}</a>'
        )

    class Meta(BaseTable.Meta):
        model = models.PhoneServiceUrl
        fields = ("button_index", "label", "url")
        default_columns = ("button_index", "label", "url")


class CSSPartitionMembershipTable(BaseTable):
    """Partition memberships embedded on CallingSearchSpace detail."""

    priority = tables.Column()
    partition = tables.LinkColumn()
    css = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.CSSPartitionMembership
        fields = ("priority", "partition", "css")
        default_columns = ("priority", "partition", "css")


class DIDAssignmentTable(BaseTable):
    """DID assignments embedded on DID, DN, or Trunk detail."""

    did = tables.LinkColumn()
    target_type = tables.Column(verbose_name="Target Type")
    assigned_at = tables.DateTimeColumn()

    class Meta(BaseTable.Meta):
        model = models.DIDAssignment
        fields = ("did", "target_type", "assigned_at")
        default_columns = ("did", "target_type", "assigned_at")


# --------------------------------------------------------------------------
# Hunt subsystem — HuntPilot, HuntList, LineGroup are first-class records;
# HuntListMember + LineGroupMember are nested-only on parent details.
# --------------------------------------------------------------------------


class HuntPilotTable(BaseTable):
    """List-view table for HuntPilot — pattern that fronts a hunt list."""

    pk = ToggleColumn()
    pattern = tables.LinkColumn()
    partition = tables.LinkColumn()
    hunt_list = tables.LinkColumn()
    actions = ButtonsColumn(models.HuntPilot)

    class Meta(BaseTable.Meta):
        model = models.HuntPilot
        fields = (
            "pk", "pattern", "partition", "hunt_list", "alerting_name",
            "description", "max_hunt_duration", "actions",
        )
        default_columns = (
            "pk", "pattern", "partition", "hunt_list", "alerting_name",
            "description", "actions",
        )


class HuntListTable(BaseTable):
    """List-view table for HuntList — ordered set of LineGroups."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.HuntList)

    class Meta(BaseTable.Meta):
        model = models.HuntList
        fields = (
            "pk", "name", "phone_system", "description",
            "route_list_enabled", "voice_mail_usage", "actions",
        )
        default_columns = (
            "pk", "name", "phone_system", "description",
            "actions",
        )


class LineGroupTable(BaseTable):
    """List-view table for LineGroup — ordered set of DNs with a hunt algo."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.LineGroup)

    class Meta(BaseTable.Meta):
        model = models.LineGroup
        fields = (
            "pk", "name", "phone_system", "distribution_algorithm",
            "rna_reversion_timeout", "hunt_algorithm_no_answer",
            "hunt_algorithm_busy", "hunt_algorithm_not_available",
            "auto_log_off_hunt", "actions",
        )
        default_columns = (
            "pk", "name", "phone_system", "distribution_algorithm",
            "rna_reversion_timeout", "actions",
        )


class HuntListMemberTable(BaseTable):
    """Members of a HuntList, embedded on HuntList detail (selection order)."""

    selection_order = tables.Column()
    line_group = tables.LinkColumn()
    hunt_list = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.HuntListMember
        fields = ("selection_order", "line_group", "hunt_list")
        default_columns = ("selection_order", "line_group")


class LineGroupMemberTable(BaseTable):
    """Members of a LineGroup, embedded on LineGroup detail (line order)."""

    line_selection_order = tables.Column(verbose_name="Order")
    directory_number = tables.LinkColumn()
    line_group = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.LineGroupMember
        fields = ("line_selection_order", "directory_number", "line_group")
        default_columns = ("line_selection_order", "directory_number")


# --------------------------------------------------------------------------
# Vendor-agnostic feature config tables — DeviceProfile, VoicemailProfile,
# CallPickupGroup. CallPickupGroupMember is nested-only on parent details.
# --------------------------------------------------------------------------


class DeviceProfileTable(BaseTable):
    """List-view table for DeviceProfile (CCM DevicePool / FreePBX template)."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    actions = ButtonsColumn(models.DeviceProfile)

    class Meta(BaseTable.Meta):
        model = models.DeviceProfile
        fields = ("pk", "name", "phone_system", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "description", "actions")


class VoicemailProfileTable(BaseTable):
    """List-view table for VoicemailProfile."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    is_default = tables.BooleanColumn(verbose_name="Default")
    actions = ButtonsColumn(models.VoicemailProfile)

    class Meta(BaseTable.Meta):
        model = models.VoicemailProfile
        fields = ("pk", "name", "phone_system", "pilot_dn", "is_default", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "pilot_dn", "is_default", "actions")


class CallPickupGroupTable(BaseTable):
    """List-view table for CallPickupGroup."""

    pk = ToggleColumn()
    name = tables.LinkColumn()
    phone_system = tables.LinkColumn()
    partition = tables.LinkColumn()
    actions = ButtonsColumn(models.CallPickupGroup)

    class Meta(BaseTable.Meta):
        model = models.CallPickupGroup
        fields = ("pk", "name", "phone_system", "pattern", "partition", "description", "actions")
        default_columns = ("pk", "name", "phone_system", "pattern", "partition", "description", "actions")


class CallPickupGroupMemberTable(BaseTable):
    """Member DNs embedded on CallPickupGroup detail (and DN detail)."""

    pickup_group = tables.LinkColumn()
    directory_number = tables.LinkColumn()
    priority = tables.Column()

    class Meta(BaseTable.Meta):
        model = models.CallPickupGroupMember
        fields = ("priority", "pickup_group", "directory_number")
        default_columns = ("priority", "directory_number")
