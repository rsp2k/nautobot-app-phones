"""Django forms for nautobot-app-phones create/edit views and filter UIs.

Each PrimaryModel/OrganizationalModel gets two forms: a `XForm`
(NautobotModelForm) for create/edit, and a `XFilterForm`
(NautobotFilterForm) for the list-view filter sidebar.

For models with ChoiceSet-backed fields, FilterForm explicitly declares
the MultipleChoiceField so users can multi-select; otherwise the auto-
generated text input is used.
"""

from django import forms
from nautobot.apps.forms import (
    DynamicModelChoiceField,
    NautobotFilterForm,
    NautobotModelForm,
)

from nautobot_phones import models


class DialPlanTraceForm(forms.Form):
    """Inputs for the dial-plan trace visualizer.

    Standalone form (not a ModelForm — the trace doesn't write
    anything). Operators pick a PhoneSystem + starting CSS + dial
    digits; the view runs ``dialplan.trace()`` and renders the result.

    Uses ``DynamicModelChoiceField`` for ``phone_system`` and
    ``starting_css`` — Nautobot's Select2-backed widget that filters
    via the REST API. Real customer clusters can have hundreds of
    CSSes; the plain ``<select>`` becomes unusable at that scale.
    """

    phone_system = DynamicModelChoiceField(
        queryset=models.PhoneSystem.objects.all(),
        help_text="The phone system whose dial plan to trace through.",
    )
    starting_css = DynamicModelChoiceField(
        queryset=models.CallingSearchSpace.objects.all(),
        # Filter the CSS dropdown by the picked phone_system. The
        # widget refreshes its results when phone_system changes.
        query_params={"phone_system": "$phone_system"},
        label="Starting CSS",
        help_text="The Calling Search Space the trace begins from "
                  "(typically the caller's CSS).",
    )
    dialed_digits = forms.CharField(
        max_length=64,
        help_text="The digits to dial. Supports literal digits, "
                  "metachars are evaluated against patterns "
                  "(e.g. '1001' matches a DN, '9.911' matches an emergency "
                  "route pattern with PreDot).",
    )
    calling_from = forms.CharField(
        max_length=64,
        required=False,
        label="Calling from (optional)",
        help_text="Originating number or phone identifier for context. "
                  "Doesn't change pattern matching in v1 — surfaces in the "
                  "result header so the trace is self-documenting.",
    )
from nautobot_phones.choices import (
    AnalogGatewayProtocolChoices,
    PhoneDeviceKindChoices,
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
# SipCircuitProfile
# --------------------------------------------------------------------------
class SipCircuitProfileForm(NautobotModelForm):
    """Create/edit form for SipCircuitProfile."""

    class Meta:
        model = models.SipCircuitProfile
        fields = (
            "circuit", "pilot_e164", "sip_sessions",
            "oli_clid_policy", "tech_support",
            "cut_sheet_received_date", "source_doc", "sensitivity",
            "vendor_extras", "tags",
        )


class SipCircuitProfileFilterForm(NautobotFilterForm):
    """Filter sidebar form for SipCircuitProfile list view."""

    model = models.SipCircuitProfile
    field_order = (
        "q", "circuit", "pilot_e164", "sip_sessions",
        "oli_clid_policy", "sensitivity",
    )
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
        fields = (
            "start_e164", "end_e164", "provider", "circuit",
            "location", "phone_system", "description", "tags",
        )


class DIDBlockFilterForm(NautobotFilterForm):
    """Filter sidebar form for DIDBlock list view."""

    model = models.DIDBlock
    field_order = ("q", "start_e164", "end_e164", "provider", "circuit", "location", "phone_system")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# DID
# --------------------------------------------------------------------------
class DIDForm(NautobotModelForm):
    """Create/edit form for DID."""

    class Meta:
        model = models.DID
        fields = ("e164", "block", "circuit", "is_special", "tags")


class DIDFilterForm(NautobotFilterForm):
    """Filter sidebar form for DID list view."""

    model = models.DID
    field_order = ("q", "e164", "block", "circuit", "is_special")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# DIDAssignment — GenericForeignKey target needs custom form handling
# --------------------------------------------------------------------------
class DIDAssignmentForm(forms.ModelForm):
    """Create/edit form for DIDAssignment.

    Uses plain ``forms.ModelForm`` (not ``NautobotModelForm``) because
    DIDAssignment subclasses ``BaseModel``, not ``PrimaryModel`` —
    so it doesn't have ``get_relationships()`` / ``cf`` / ``tags``
    surface that the Nautobot mixins assume. The model is a join,
    not a primary entity; the lighter form base fits.

    The ORM stores the target via a GenericForeignKey
    (``target_type`` + ``target_id``). A raw form on those fields would
    show a ContentType dropdown plus a UUID text input — accurate but
    unfriendly. Instead, expose two optional FK fields and validate
    XOR: exactly one of (target_directorynumber, target_trunk) must
    be set. On save, derive ``target_type`` + ``target_id`` from the
    populated field.

    Future kinds (e.g. Voicemail target) extend by adding another
    optional FK field + an entry in the XOR check + the save
    dispatch.
    """

    target_directorynumber = forms.ModelChoiceField(
        queryset=models.DirectoryNumber.objects.all(),
        required=False,
        label="Target Directory Number",
        help_text="If this DID rings an extension, pick the Directory Number here.",
    )
    target_trunk = forms.ModelChoiceField(
        queryset=models.Trunk.objects.all(),
        required=False,
        label="Target Trunk",
        help_text="If this DID is owned by a downstream PBX reached over a trunk, "
                  "pick that trunk here.",
    )

    class Meta:
        model = models.DIDAssignment
        # ``target_type`` and ``target_id`` are set in save() from the
        # two optional FK fields above; we don't expose them directly.
        fields = ("did",)

    def __init__(self, *args, **kwargs):
        """Pre-populate the appropriate target field when editing."""
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.target:
            target = self.instance.target
            if isinstance(target, models.DirectoryNumber):
                self.fields["target_directorynumber"].initial = target.pk
            elif isinstance(target, models.Trunk):
                self.fields["target_trunk"].initial = target.pk

    def clean(self):
        """Enforce: exactly one target FK is set."""
        cleaned = super().clean()
        dn = cleaned.get("target_directorynumber")
        trunk = cleaned.get("target_trunk")
        if not dn and not trunk:
            raise forms.ValidationError(
                "Pick exactly one target: a Directory Number OR a Trunk.",
            )
        if dn and trunk:
            raise forms.ValidationError(
                "Pick only one target — both a Directory Number and a Trunk "
                "were selected.",
            )
        return cleaned

    def save(self, commit=True):
        """Resolve the chosen target to (target_type, target_id) before save."""
        from django.contrib.contenttypes.models import ContentType
        target_obj = (
            self.cleaned_data.get("target_directorynumber")
            or self.cleaned_data.get("target_trunk")
        )
        self.instance.target_type = ContentType.objects.get_for_model(target_obj)
        self.instance.target_id = target_obj.pk
        return super().save(commit=commit)


class DIDAssignmentFilterForm(NautobotFilterForm):
    """Filter sidebar form for DIDAssignment list view."""

    model = models.DIDAssignment
    field_order = ("q", "did", "target_type")
    q = forms.CharField(required=False, label="Search")
    # target_type is rendered as a ContentType picker constrained to
    # the same limit_choices_to as the model field (DN or Trunk).


# --------------------------------------------------------------------------
# Phone
# --------------------------------------------------------------------------
class PhoneForm(NautobotModelForm):
    """Create/edit form for Phone."""

    class Meta:
        model = models.Phone
        fields = (
            # Identity
            "device_name", "device_kind", "mac_address", "description", "phone_system", "device",
            "registration_status", "last_registered_ip",
            "media_zone",
            # Device Profile (vendor-agnostic device-config bundle)
            "device_profile",
            "owner_user_id", "user_locale",
            "dnd_status",
            # Vendor-specific long-tail
            "vendor_extras", "tags",
        )


class PhoneFilterForm(NautobotFilterForm):
    """Filter sidebar form for Phone list view."""

    model = models.Phone
    field_order = ("q", "device_name", "device_kind", "mac_address", "phone_system", "registration_status", "device_profile", "owner_user_id", "media_zone")
    q = forms.CharField(required=False, label="Search")
    device_kind = forms.MultipleChoiceField(choices=PhoneDeviceKindChoices, required=False, label="Device Kind")
    registration_status = forms.MultipleChoiceField(choices=RegistrationStatusChoices, required=False)


# --------------------------------------------------------------------------
# Trunk
# --------------------------------------------------------------------------
class TrunkForm(NautobotModelForm):
    """Create/edit form for Trunk."""

    class Meta:
        model = models.Trunk
        fields = (
            "name", "phone_system", "trunk_type",
            "destination_address", "destination_port",
            "css", "inbound_css", "circuit",
            "vendor_extras", "tags",
        )


class TrunkFilterForm(NautobotFilterForm):
    """Filter sidebar form for Trunk list view."""

    model = models.Trunk
    field_order = ("q", "name", "phone_system", "trunk_type", "destination_address", "css", "circuit")
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


# --------------------------------------------------------------------------
# Hunt subsystem — HuntPilot, HuntList, LineGroup
# Member tables (HuntListMember, LineGroupMember) don't get standalone
# forms; they're created through the parent's M2M widget or by sync.
# --------------------------------------------------------------------------
class HuntPilotForm(NautobotModelForm):
    """Create/edit form for HuntPilot."""

    class Meta:
        model = models.HuntPilot
        fields = (
            "pattern", "partition", "hunt_list", "alerting_name",
            "description", "max_hunt_duration",
            "forward_hunt_no_answer_destination", "forward_hunt_busy_destination",
            "vendor_extras", "tags",
        )


class HuntPilotFilterForm(NautobotFilterForm):
    """Filter sidebar form for HuntPilot list view."""

    model = models.HuntPilot
    field_order = ("q", "pattern", "partition", "hunt_list")
    q = forms.CharField(required=False, label="Search")


class HuntListForm(NautobotModelForm):
    """Create/edit form for HuntList."""

    class Meta:
        model = models.HuntList
        fields = (
            "name", "phone_system", "description",
            "route_list_enabled", "voice_mail_usage", "vendor_extras", "tags",
        )


class HuntListFilterForm(NautobotFilterForm):
    """Filter sidebar form for HuntList list view."""

    model = models.HuntList
    field_order = ("q", "name", "phone_system")
    q = forms.CharField(required=False, label="Search")


class LineGroupForm(NautobotModelForm):
    """Create/edit form for LineGroup."""

    class Meta:
        model = models.LineGroup
        fields = (
            "name", "phone_system", "distribution_algorithm",
            "rna_reversion_timeout",
            "hunt_algorithm_no_answer", "hunt_algorithm_busy",
            "hunt_algorithm_not_available", "auto_log_off_hunt",
            "vendor_extras", "tags",
        )


class LineGroupFilterForm(NautobotFilterForm):
    """Filter sidebar form for LineGroup list view."""

    model = models.LineGroup
    field_order = ("q", "name", "phone_system", "distribution_algorithm")
    q = forms.CharField(required=False, label="Search")


# --------------------------------------------------------------------------
# Vendor-agnostic feature config forms — DeviceProfile, VoicemailProfile,
# CallPickupGroup.
# --------------------------------------------------------------------------
class DeviceProfileForm(NautobotModelForm):
    """Create/edit form for DeviceProfile."""

    class Meta:
        model = models.DeviceProfile
        fields = ("name", "phone_system", "description", "vendor_extras", "tags")


class DeviceProfileFilterForm(NautobotFilterForm):
    """Filter sidebar form for DeviceProfile list view."""

    model = models.DeviceProfile
    field_order = ("q", "name", "phone_system")
    q = forms.CharField(required=False, label="Search")


class VoicemailProfileForm(NautobotModelForm):
    """Create/edit form for VoicemailProfile."""

    class Meta:
        model = models.VoicemailProfile
        fields = ("name", "phone_system", "description", "pilot_dn", "is_default", "vendor_extras", "tags")


class VoicemailProfileFilterForm(NautobotFilterForm):
    """Filter sidebar form for VoicemailProfile list view."""

    model = models.VoicemailProfile
    field_order = ("q", "name", "phone_system", "is_default")
    q = forms.CharField(required=False, label="Search")


class CallPickupGroupForm(NautobotModelForm):
    """Create/edit form for CallPickupGroup."""

    class Meta:
        model = models.CallPickupGroup
        fields = ("name", "phone_system", "pattern", "partition", "description", "vendor_extras", "tags")


class CallPickupGroupFilterForm(NautobotFilterForm):
    """Filter sidebar form for CallPickupGroup list view."""

    model = models.CallPickupGroup
    field_order = ("q", "name", "phone_system", "pattern", "partition")
    q = forms.CharField(required=False, label="Search")
