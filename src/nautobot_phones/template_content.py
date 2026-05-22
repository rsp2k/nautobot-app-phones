"""Detail-view template extensions for nautobot-app-phones.

Adds a 'Vendor Extras' KeyValueTablePanel to the detail views of models
that carry the `vendor_extras` JSONField — DirectoryNumber, Phone, Trunk,
AnalogGateway. The panel renders the JSON as a clean two-column table.

Also injects DID-inventory panels onto core ``circuits.Circuit`` detail
pages — so an operator viewing a SIP trunk circuit sees the DID blocks
and individual DIDs that ride over it, without having to navigate away
to our DID-blocks / DIDs list views.

Discovered by Nautobot via the module-level `template_extensions` list,
matched against the convention `nautobot_phones.template_content`.
"""

from nautobot.apps.ui import (
    KeyValueTablePanel,
    ObjectsTablePanel,
    Panel,
    SectionChoices,
    TemplateExtension,
)

from nautobot_phones import tables
from nautobot_phones.heatmap import build_heatmap_data


def _circuit_sip_profile(circuit):
    """Return the SipCircuitProfile for a circuit, or None if it has no SIP profile.

    The reverse OneToOne raises ``SipCircuitProfile.DoesNotExist`` when no
    profile exists for the circuit. Catch it and return None so callers
    can use a simple truthiness check.
    """
    if circuit is None:
        return None
    try:
        return circuit.sip_profile
    except Exception:  # pragma: no cover - DoesNotExist subclass varies by Django version
        return None


class CircuitDIDHeatmapPanel(Panel):
    """DID inventory heatmap, surfaced on the core circuits.Circuit detail page.

    Only renders when the Circuit has a [SipCircuitProfile][profile] attached —
    i.e. when the Circuit represents a SIP trunk. Non-SIP circuits (Internet
    transit, MPLS, cross-connects, etc.) keep the existing core detail layout
    unchanged.

    [profile]: ../../models/sipcircuitprofile/
    """

    label = "DID Heatmap"
    body_content_template_path = "nautobot_phones/inc/did_heatmap.html"

    def get_extra_context(self, context):
        """Resolve circuit → profile → heatmap data."""
        ctx = super().get_extra_context(context) if hasattr(super(), "get_extra_context") else {}
        profile = _circuit_sip_profile(context.get("object"))
        if profile is not None:
            ctx["profile"] = profile
            ctx["heatmap"] = build_heatmap_data(profile)
        return ctx

    def render_body_content(self, context):
        """Merge heatmap data into context, then delegate to the template path."""
        context.update(self.get_extra_context(context))
        return super().render_body_content(context)

    def should_render(self, context):
        """Skip the panel entirely when the Circuit isn't a SIP trunk."""
        return _circuit_sip_profile(context.get("object")) is not None


class VendorExtrasPanel(KeyValueTablePanel):
    """KeyValueTablePanel subclass that pulls its data from the object's vendor_extras."""

    def __init__(self, **kwargs):
        """Default to a sensible label and weight; overridable per-extension."""
        kwargs.setdefault("label", "Vendor Extras")
        # Place after the standard panels (Custom Fields ~700, Tags ~800).
        kwargs.setdefault("weight", 750)
        super().__init__(**kwargs)

    def get_data(self, context):
        """Pull vendor_extras dict off the object in context."""
        obj = context.get("object")
        if obj is None:
            return {}
        return getattr(obj, "vendor_extras", None) or {}

    def should_render(self, context):
        """Only render when the object actually has vendor_extras populated."""
        return bool(self.get_data(context))


class _VendorExtrasMixin:
    """Mixin: a single panel showing the object's vendor_extras."""

    object_detail_panels = (VendorExtrasPanel(),)


class DirectoryNumberExtension(_VendorExtrasMixin, TemplateExtension):
    """Vendor Extras panel on DirectoryNumber detail."""

    model = "nautobot_phones.directorynumber"


class PhoneExtension(_VendorExtrasMixin, TemplateExtension):
    """Vendor Extras panel on Phone detail."""

    model = "nautobot_phones.phone"


class TrunkExtension(_VendorExtrasMixin, TemplateExtension):
    """Vendor Extras panel on Trunk detail."""

    model = "nautobot_phones.trunk"


class AnalogGatewayExtension(_VendorExtrasMixin, TemplateExtension):
    """Vendor Extras panel on AnalogGateway detail."""

    model = "nautobot_phones.analoggateway"


class CircuitExtension(TemplateExtension):
    """Inject DID inventory + PBX-trunk panels into the core Circuit detail page.

    Operators viewing a SIP carrier circuit naturally ask "what DIDs does
    this trunk deliver?" and "which PBX-side Trunks terminate here?". The
    answer lives in our app's models — we surface it directly on the core
    Circuit detail page rather than asking users to navigate to the DID
    Blocks / DIDs / Trunks list views and filter by hand.
    """

    model = "circuits.circuit"

    object_detail_panels = (
        ObjectsTablePanel(
            section=SectionChoices.RIGHT_HALF, weight=600,
            table_class=tables.DIDBlockTable, table_filter="circuit",
            table_title="DID Blocks on this Circuit",
            exclude_columns=["circuit"],
        ),
        ObjectsTablePanel(
            section=SectionChoices.RIGHT_HALF, weight=650,
            table_class=tables.DIDTable, table_filter="circuit",
            table_title="Individual DIDs on this Circuit",
            exclude_columns=["circuit"],
        ),
        ObjectsTablePanel(
            section=SectionChoices.RIGHT_HALF, weight=700,
            table_class=tables.TrunkTable, table_filter="circuit",
            table_title="PBX Trunks Terminating this Circuit",
            exclude_columns=["circuit"],
        ),
        # Full-width DID heatmap below the per-table panels. Only renders
        # for circuits that have a SipCircuitProfile attached (i.e. SIP
        # trunks); see CircuitDIDHeatmapPanel.should_render.
        CircuitDIDHeatmapPanel(
            section=SectionChoices.FULL_WIDTH, weight=800,
        ),
    )


template_extensions = [
    DirectoryNumberExtension,
    PhoneExtension,
    TrunkExtension,
    AnalogGatewayExtension,
    CircuitExtension,
]
