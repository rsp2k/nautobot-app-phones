"""ViewSets for nautobot-app-phones.

Each PrimaryModel/OrganizationalModel gets a NautobotUIViewSet that bundles
list, detail, create, edit, delete, and bulk-action views together. Each
viewset also declares `object_detail_content` — a layout of panels that
render on the detail page (model fields on the left, related-object
tables on the right).

Junction-style records (Line, AnalogPort, CSSPartitionMembership,
DIDAssignment) don't have viewsets — they render nested in their parent's
detail view via ObjectsTablePanel.
"""

from django.utils.html import format_html
from nautobot.apps.ui import (
    ObjectDetailContent,
    ObjectFieldsPanel,
    ObjectsTablePanel,
    SectionChoices,
)
from nautobot.apps.views import NautobotUIViewSet


def _https_link(value):
    """Render an IP/hostname as an HTTPS link to the device's admin UI.

    Cisco phones expose an admin web interface at https://<ip>/ — clicking
    the IP in the detail view opens that admin UI in a new tab.
    """
    if not value:
        return value
    return format_html('<a href="https://{0}/" target="_blank" rel="noopener noreferrer">{0}</a>', value)

from nautobot_phones import filters, forms, models, tables


class PhoneSystemUIViewSet(NautobotUIViewSet):
    """CRUD viewset for PhoneSystem."""

    queryset = models.PhoneSystem.objects.all()
    table_class = tables.PhoneSystemTable
    filterset_class = filters.PhoneSystemFilterSet
    filterset_form_class = forms.PhoneSystemFilterForm
    form_class = forms.PhoneSystemForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF,
                weight=100,
                fields=["name", "vendor", "version", "hostname", "secrets_group", "location", "last_synced_at"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.PartitionTable, table_filter="phone_system",
                table_title="Partitions", exclude_columns=["phone_system"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.CallingSearchSpaceTable, table_filter="phone_system",
                table_title="Calling Search Spaces", exclude_columns=["phone_system"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=300,
                table_class=tables.PhoneTable, table_filter="phone_system",
                table_title="Phones", exclude_columns=["phone_system"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=400,
                table_class=tables.TrunkTable, table_filter="phone_system",
                table_title="Trunks", exclude_columns=["phone_system"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=500,
                table_class=tables.AnalogGatewayTable, table_filter="phone_system",
                table_title="Analog Gateways", exclude_columns=["phone_system"],
            ),
        ),
    )


class CarrierUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Carrier."""

    queryset = models.Carrier.objects.all()
    table_class = tables.CarrierTable
    filterset_class = filters.CarrierFilterSet
    filterset_form_class = forms.CarrierFilterForm
    form_class = forms.CarrierForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "description", "account_number"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.DIDBlockTable, table_filter="carrier",
                table_title="DID Blocks", exclude_columns=["carrier"],
            ),
        ),
    )


class PartitionUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Partition."""

    queryset = models.Partition.objects.all()
    table_class = tables.PartitionTable
    filterset_class = filters.PartitionFilterSet
    filterset_form_class = forms.PartitionFilterForm
    form_class = forms.PartitionForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "phone_system", "description"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.DirectoryNumberTable, table_filter="partition",
                table_title="Directory Numbers", exclude_columns=["partition"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.RoutePatternTable, table_filter="partition",
                table_title="Route Patterns", exclude_columns=["partition"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=300,
                table_class=tables.TranslationPatternTable, table_filter="partition",
                table_title="Translation Patterns", exclude_columns=["partition"],
            ),
        ),
    )


class CallingSearchSpaceUIViewSet(NautobotUIViewSet):
    """CRUD viewset for CallingSearchSpace."""

    queryset = models.CallingSearchSpace.objects.all()
    table_class = tables.CallingSearchSpaceTable
    filterset_class = filters.CallingSearchSpaceFilterSet
    filterset_form_class = forms.CallingSearchSpaceFilterForm
    form_class = forms.CallingSearchSpaceForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "phone_system", "description"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.CSSPartitionMembershipTable, table_filter="css",
                table_title="Partition Members (in priority order)", exclude_columns=["css"],
                order_by_fields=["priority"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.RoutePatternTable, table_filter="css",
                table_title="Route Patterns Using This CSS", exclude_columns=["css"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=300,
                table_class=tables.TranslationPatternTable, table_filter="css",
                table_title="Translation Patterns Using This CSS", exclude_columns=["css"],
            ),
        ),
    )


class DirectoryNumberUIViewSet(NautobotUIViewSet):
    """CRUD viewset for DirectoryNumber."""

    queryset = models.DirectoryNumber.objects.all()
    table_class = tables.DirectoryNumberTable
    filterset_class = filters.DirectoryNumberFilterSet
    filterset_form_class = forms.DirectoryNumberFilterForm
    form_class = forms.DirectoryNumberForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["extension", "partition", "phone_system", "alerting_name", "voicemail_profile"],
                key_transforms={"extension": "Directory Number"},
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.LineTable, table_filter="directory_number",
                table_title="Lines (phone-button appearances)", exclude_columns=["directory_number"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.AnalogPortTable, table_filter="directory_number",
                table_title="Analog Ports", exclude_columns=["directory_number"],
            ),
        ),
    )


class DIDBlockUIViewSet(NautobotUIViewSet):
    """CRUD viewset for DIDBlock."""

    queryset = models.DIDBlock.objects.all()
    table_class = tables.DIDBlockTable
    filterset_class = filters.DIDBlockFilterSet
    filterset_form_class = forms.DIDBlockFilterForm
    form_class = forms.DIDBlockForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["start_e164", "end_e164", "size", "carrier", "location", "phone_system", "description"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.DIDTable, table_filter="block",
                table_title="Materialized DIDs", exclude_columns=["block"],
            ),
        ),
    )


class DIDUIViewSet(NautobotUIViewSet):
    """CRUD viewset for DID."""

    queryset = models.DID.objects.all()
    table_class = tables.DIDTable
    filterset_class = filters.DIDFilterSet
    filterset_form_class = forms.DIDFilterForm
    form_class = forms.DIDForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["e164", "block", "is_special"],
            ),
        ),
    )


class PhoneUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Phone."""

    queryset = models.Phone.objects.all()
    table_class = tables.PhoneTable
    filterset_class = filters.PhoneFilterSet
    filterset_form_class = forms.PhoneFilterForm
    form_class = forms.PhoneForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            # ---- Left column: identity + organizational metadata ----
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                label="Phone",
                fields=[
                    "device_name", "description", "mac_address", "model",
                    "phone_system", "device", "location",  # `location` is a @property reading device.location
                    "ccm_location", "network_location",
                    "registration_status", "last_registered_ip",
                ],
                key_transforms={"location": "Physical Location (from Device)"},
                value_transforms={"last_registered_ip": [_https_link]},
            ),
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=200,
                label="Device Information",
                fields=[
                    "device_pool", "common_phone_profile", "common_device_configuration",
                    "phone_button_template", "softkey_template",
                    "owner_user_id", "mobility_user_id",
                    "built_in_bridge", "privacy", "device_mobility_mode",
                    "always_use_prime_line", "always_use_prime_line_for_voice",
                    "user_locale", "network_locale", "aar_neighborhood",
                    "dnd_status", "dnd_option",
                ],
            ),
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=300,
                label="Protocol Specific Information",
                fields=[
                    "device_security_profile", "sip_profile",
                    "rerouting_css", "subscribe_css",
                    "mtp_required", "packet_capture_mode",
                ],
            ),
            # ---- Right column: button configuration ----
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.LineTable, table_filter="phone",
                table_title="Lines (phone buttons)", exclude_columns=["phone"],
                order_by_fields=["button_index"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.SpeedDialTable, table_filter="phone",
                table_title="Speed Dials", exclude_columns=["phone"],
                order_by_fields=["button_index"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=300,
                table_class=tables.PhoneServiceUrlTable, table_filter="phone",
                table_title="Service URLs", exclude_columns=["phone"],
                order_by_fields=["button_index"],
            ),
        ),
    )


class TrunkUIViewSet(NautobotUIViewSet):
    """CRUD viewset for Trunk."""

    queryset = models.Trunk.objects.all()
    table_class = tables.TrunkTable
    filterset_class = filters.TrunkFilterSet
    filterset_form_class = forms.TrunkFilterForm
    form_class = forms.TrunkForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "phone_system", "trunk_type", "destination_address", "destination_port", "css", "inbound_css"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.RoutePatternTable, table_filter="target_trunk",
                table_title="Route Patterns Targeting This Trunk", exclude_columns=["target_trunk"],
            ),
        ),
    )


class RouteListUIViewSet(NautobotUIViewSet):
    """CRUD viewset for RouteList."""

    queryset = models.RouteList.objects.all()
    table_class = tables.RouteListTable
    filterset_class = filters.RouteListFilterSet
    filterset_form_class = forms.RouteListFilterForm
    form_class = forms.RouteListForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "phone_system", "description"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.RouteListMemberTable, table_filter="route_list",
                table_title="Member Route Groups (priority order)", exclude_columns=["route_list"],
                order_by_fields=["priority"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.RoutePatternTable, table_filter="target_route_list",
                table_title="Route Patterns Targeting This List", exclude_columns=["target_route_list"],
            ),
        ),
    )


class RouteGroupUIViewSet(NautobotUIViewSet):
    """CRUD viewset for RouteGroup."""

    queryset = models.RouteGroup.objects.all()
    table_class = tables.RouteGroupTable
    filterset_class = filters.RouteGroupFilterSet
    filterset_form_class = forms.RouteGroupFilterForm
    form_class = forms.RouteGroupForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "phone_system", "distribution_algorithm", "description"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.RouteGroupMemberTable, table_filter="route_group",
                table_title="Member Devices (priority order)", exclude_columns=["route_group"],
                order_by_fields=["priority"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                table_class=tables.RouteListMemberTable, table_filter="route_group",
                table_title="Route Lists Containing This Group", exclude_columns=["route_group"],
            ),
        ),
    )


class RoutePatternUIViewSet(NautobotUIViewSet):
    """CRUD viewset for RoutePattern."""

    queryset = models.RoutePattern.objects.all()
    table_class = tables.RoutePatternTable
    filterset_class = filters.RoutePatternFilterSet
    filterset_form_class = forms.RoutePatternFilterForm
    form_class = forms.RoutePatternForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["pattern", "partition", "css", "target_trunk", "target_route_list", "target_dn", "urgent", "discard_digits"],
            ),
        ),
    )


class TranslationPatternUIViewSet(NautobotUIViewSet):
    """CRUD viewset for TranslationPattern.

    Translation patterns transform dialed digits BEFORE the route-pattern
    engine evaluates them — e.g. `911 → CER` rewrites a 3-digit emergency
    call into the digits the CER trunk wants. The translated digits get
    re-injected into the dial plan, so unlike RoutePattern there's no
    target-trunk / target-DN field.

    Detail layout mirrors the CCM admin form's three sections (Pattern
    Definition, Calling Party Transformations, Called Party Transformations)
    so operators jumping between Nautobot and the CCM admin UI see the
    same field grouping in both places.
    """

    queryset = models.TranslationPattern.objects.all()
    table_class = tables.TranslationPatternTable
    filterset_class = filters.TranslationPatternFilterSet
    filterset_form_class = forms.TranslationPatternFilterForm
    form_class = forms.TranslationPatternForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                label="Pattern Definition",
                fields=[
                    "pattern", "partition", "css", "description",
                    "block_enable", "release_clause", "urgent_priority",
                    "provide_outside_dial_tone", "use_originator_css",
                    "dont_wait_for_idt", "route_next_hop_by_cgpn",
                    "is_emergency_service_number", "route_class",
                ],
            ),
            ObjectFieldsPanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                label="Calling Party Transformations",
                fields=[
                    "use_calling_party_phone_mask",
                    "calling_party_transformation_mask",
                    "calling_party_prefix_digits",
                ],
            ),
            ObjectFieldsPanel(
                section=SectionChoices.RIGHT_HALF, weight=200,
                label="Called Party Transformations",
                fields=[
                    "digit_discard_instruction",
                    "called_party_transformation_mask",
                    "prefix_digits_out",
                ],
            ),
        ),
    )


class AnalogGatewayUIViewSet(NautobotUIViewSet):
    """CRUD viewset for AnalogGateway."""

    queryset = models.AnalogGateway.objects.all()
    table_class = tables.AnalogGatewayTable
    filterset_class = filters.AnalogGatewayFilterSet
    filterset_form_class = forms.AnalogGatewayFilterForm
    form_class = forms.AnalogGatewayForm
    serializer_class = None
    lookup_field = "pk"

    object_detail_content = ObjectDetailContent(
        panels=(
            ObjectFieldsPanel(
                section=SectionChoices.LEFT_HALF, weight=100,
                fields=["name", "phone_system", "location", "device", "model", "protocol"],
            ),
            ObjectsTablePanel(
                section=SectionChoices.RIGHT_HALF, weight=100,
                table_class=tables.AnalogPortTable, table_filter="gateway",
                table_title="Ports", exclude_columns=["gateway"],
            ),
        ),
    )
