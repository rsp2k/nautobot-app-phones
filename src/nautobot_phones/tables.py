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
    """List-view table for Phone."""

    pk = ToggleColumn()
    device_name = tables.LinkColumn()
    mac_address = tables.Column()
    phone_system = tables.LinkColumn()
    location = tables.LinkColumn()
    actions = ButtonsColumn(models.Phone)

    class Meta(BaseTable.Meta):
        model = models.Phone
        fields = ("pk", "device_name", "mac_address", "model", "description", "phone_system", "location", "registration_status", "last_registered_ip", "actions")
        default_columns = ("pk", "device_name", "description", "mac_address", "model", "phone_system", "last_registered_ip", "actions")


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
    """Lines (phone-button appearances) — embedded on Phone or DN detail."""

    button_index = tables.Column()
    phone = tables.LinkColumn()
    directory_number = tables.LinkColumn()

    class Meta(BaseTable.Meta):
        model = models.Line
        fields = ("button_index", "phone", "directory_number", "label", "ring_setting")
        default_columns = ("button_index", "phone", "directory_number", "label")


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
    """List-view table for TranslationPattern."""

    pk = ToggleColumn()
    pattern = tables.LinkColumn()
    partition = tables.LinkColumn()
    css = tables.LinkColumn()
    actions = ButtonsColumn(models.TranslationPattern)

    class Meta(BaseTable.Meta):
        model = models.TranslationPattern
        fields = ("pk", "pattern", "partition", "css", "description", "actions")
        default_columns = ("pk", "pattern", "partition", "css", "description", "actions")


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
