"""Django forms for nautobot-app-phones create/edit views and filter UIs.

Each PrimaryModel/OrganizationalModel gets two forms: a `XForm`
(NautobotModelForm) for create/edit, and a `XFilterForm`
(NautobotFilterForm) for the list-view filter sidebar.

For models with ChoiceSet-backed fields, FilterForm explicitly declares
the MultipleChoiceField so users can multi-select; otherwise the auto-
generated text input is used.
"""

from django import forms
from nautobot.apps.forms import NautobotFilterForm, NautobotModelForm

from nautobot_phones import models
from nautobot_phones.choices import (
    AnalogGatewayProtocolChoices,
    RegistrationStatusChoices,
    TrunkTypeChoices,
    VendorChoices,
)


# --------------------------------------------------------------------------
# PhoneSystem
# --------------------------------------------------------------------------
class PhoneSystemForm(NautobotModelForm):
    """Create/edit form for PhoneSystem."""

    class Meta:
        model = models.PhoneSystem
        fields = ("name", "vendor", "version", "hostname", "secrets_group", "location", "delete_policy", "tags")


class PhoneSystemFilterForm(NautobotFilterForm):
    """Filter sidebar form for PhoneSystem list view."""

    model = models.PhoneSystem
    field_order = ("q", "name", "vendor", "version", "hostname", "location")

    q = forms.CharField(required=False, label="Search")
    vendor = forms.MultipleChoiceField(choices=VendorChoices, required=False)


# --------------------------------------------------------------------------
# Carrier
# --------------------------------------------------------------------------
class CarrierForm(NautobotModelForm):
    """Create/edit form for Carrier."""

    class Meta:
        model = models.Carrier
        fields = ("name", "description", "account_number")


class CarrierFilterForm(NautobotFilterForm):
    """Filter sidebar form for Carrier list view."""

    model = models.Carrier
    field_order = ("q", "name", "account_number")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# Partition
# --------------------------------------------------------------------------
class PartitionForm(NautobotModelForm):
    """Create/edit form for Partition."""

    class Meta:
        model = models.Partition
        fields = ("name", "phone_system", "description")


class PartitionFilterForm(NautobotFilterForm):
    """Filter sidebar form for Partition list view."""

    model = models.Partition
    field_order = ("q", "name", "phone_system")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# CallingSearchSpace
# --------------------------------------------------------------------------
class CallingSearchSpaceForm(NautobotModelForm):
    """Create/edit form for CallingSearchSpace."""

    class Meta:
        model = models.CallingSearchSpace
        fields = ("name", "phone_system", "description")


class CallingSearchSpaceFilterForm(NautobotFilterForm):
    """Filter sidebar form for CallingSearchSpace list view."""

    model = models.CallingSearchSpace
    field_order = ("q", "name", "phone_system")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# DirectoryNumber
# --------------------------------------------------------------------------
class DirectoryNumberForm(NautobotModelForm):
    """Create/edit form for DirectoryNumber."""

    class Meta:
        model = models.DirectoryNumber
        fields = ("extension", "partition", "phone_system", "alerting_name", "voicemail_profile", "vendor_extras", "tags")


class DirectoryNumberFilterForm(NautobotFilterForm):
    """Filter sidebar form for DirectoryNumber list view."""

    model = models.DirectoryNumber
    field_order = ("q", "extension", "partition", "phone_system", "alerting_name")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# DIDBlock
# --------------------------------------------------------------------------
class DIDBlockForm(NautobotModelForm):
    """Create/edit form for DIDBlock."""

    class Meta:
        model = models.DIDBlock
        fields = ("start_e164", "end_e164", "carrier", "location", "phone_system", "description", "tags")


class DIDBlockFilterForm(NautobotFilterForm):
    """Filter sidebar form for DIDBlock list view."""

    model = models.DIDBlock
    field_order = ("q", "start_e164", "end_e164", "carrier", "location", "phone_system")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# DID
# --------------------------------------------------------------------------
class DIDForm(NautobotModelForm):
    """Create/edit form for DID."""

    class Meta:
        model = models.DID
        fields = ("e164", "block", "is_special", "tags")


class DIDFilterForm(NautobotFilterForm):
    """Filter sidebar form for DID list view."""

    model = models.DID
    field_order = ("q", "e164", "block", "is_special")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# Phone
# --------------------------------------------------------------------------
class PhoneForm(NautobotModelForm):
    """Create/edit form for Phone."""

    class Meta:
        model = models.Phone
        fields = (
            # Identity
            "device_name", "mac_address", "description", "phone_system", "device",
            "registration_status", "last_registered_ip",
            "ccm_location", "network_location",
            # Device Information
            "device_pool", "common_phone_profile", "common_device_configuration",
            "phone_button_template", "softkey_template",
            "owner_user_id", "mobility_user_id",
            "built_in_bridge", "privacy", "device_mobility_mode",
            "always_use_prime_line", "always_use_prime_line_for_voice",
            "user_locale", "network_locale", "aar_neighborhood",
            "dnd_status", "dnd_option",
            # Protocol Specific Information
            "device_security_profile", "sip_profile", "rerouting_css", "subscribe_css",
            "mtp_required", "packet_capture_mode",
            # Misc
            "vendor_extras", "tags",
        )


class PhoneFilterForm(NautobotFilterForm):
    """Filter sidebar form for Phone list view."""

    model = models.Phone
    field_order = ("q", "device_name", "mac_address", "phone_system", "registration_status", "device_pool", "owner_user_id", "ccm_location")
    q = forms.CharField(required=False, label="Search")
    registration_status = forms.MultipleChoiceField(choices=RegistrationStatusChoices, required=False)


# --------------------------------------------------------------------------
# Trunk
# --------------------------------------------------------------------------
class TrunkForm(NautobotModelForm):
    """Create/edit form for Trunk."""

    class Meta:
        model = models.Trunk
        fields = ("name", "phone_system", "trunk_type", "destination_address", "destination_port", "css", "inbound_css", "vendor_extras", "tags")


class TrunkFilterForm(NautobotFilterForm):
    """Filter sidebar form for Trunk list view."""

    model = models.Trunk
    field_order = ("q", "name", "phone_system", "trunk_type", "destination_address", "css")
    q = forms.CharField(required=False, label="Search")
    trunk_type = forms.MultipleChoiceField(choices=TrunkTypeChoices, required=False)


# --------------------------------------------------------------------------
# RouteList
# --------------------------------------------------------------------------
class RouteListForm(NautobotModelForm):
    """Create/edit form for RouteList."""

    class Meta:
        model = models.RouteList
        fields = ("name", "phone_system", "description", "vendor_extras", "tags")


class RouteListFilterForm(NautobotFilterForm):
    """Filter sidebar form for RouteList list view."""

    model = models.RouteList
    field_order = ("q", "name", "phone_system")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# RouteGroup
# --------------------------------------------------------------------------
class RouteGroupForm(NautobotModelForm):
    """Create/edit form for RouteGroup."""

    class Meta:
        model = models.RouteGroup
        fields = ("name", "phone_system", "description", "distribution_algorithm", "vendor_extras", "tags")


class RouteGroupFilterForm(NautobotFilterForm):
    """Filter sidebar form for RouteGroup list view."""

    model = models.RouteGroup
    field_order = ("q", "name", "phone_system", "distribution_algorithm")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# RoutePattern
# --------------------------------------------------------------------------
class RoutePatternForm(NautobotModelForm):
    """Create/edit form for RoutePattern."""

    class Meta:
        model = models.RoutePattern
        fields = ("pattern", "partition", "css", "target_trunk", "target_route_list", "target_dn", "urgent", "discard_digits", "tags")


class RoutePatternFilterForm(NautobotFilterForm):
    """Filter sidebar form for RoutePattern list view."""

    model = models.RoutePattern
    field_order = ("q", "pattern", "partition", "css", "target_trunk", "target_route_list", "target_dn", "urgent")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# TranslationPattern
# --------------------------------------------------------------------------
class TranslationPatternForm(NautobotModelForm):
    """Create/edit form for TranslationPattern.

    Field order mirrors the CCM admin form: Pattern Definition first,
    then Calling Party Transformations, then Called Party Transformations.
    """

    class Meta:
        model = models.TranslationPattern
        fields = (
            # Pattern Definition
            "pattern", "partition", "css", "description",
            "block_enable", "release_clause", "urgent_priority",
            "provide_outside_dial_tone", "use_originator_css",
            "dont_wait_for_idt", "route_next_hop_by_cgpn",
            "is_emergency_service_number", "route_class",
            # Calling Party Transformations
            "use_calling_party_phone_mask", "calling_party_transformation_mask",
            "calling_party_prefix_digits",
            # Called Party Transformations
            "digit_discard_instruction", "called_party_transformation_mask",
            "prefix_digits_out",
            # Misc
            "vendor_extras", "tags",
        )


class TranslationPatternFilterForm(NautobotFilterForm):
    """Filter sidebar form for TranslationPattern list view."""

    model = models.TranslationPattern
    field_order = ("q", "pattern", "partition", "css")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# AnalogGateway
# --------------------------------------------------------------------------
class AnalogGatewayForm(NautobotModelForm):
    """Create/edit form for AnalogGateway."""

    class Meta:
        model = models.AnalogGateway
        fields = ("name", "phone_system", "location", "device", "model", "protocol", "vendor_extras", "tags")


class AnalogGatewayFilterForm(NautobotFilterForm):
    """Filter sidebar form for AnalogGateway list view."""

    model = models.AnalogGateway
    field_order = ("q", "name", "phone_system", "location", "model", "protocol")
    q = forms.CharField(required=False, label="Search")
    protocol = forms.MultipleChoiceField(choices=AnalogGatewayProtocolChoices, required=False)
