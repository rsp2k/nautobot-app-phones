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
    SectionChoices,
    TemplateExtension,
)

from nautobot_phones import tables


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
    )


template_extensions = [
    DirectoryNumberExtension,
    PhoneExtension,
    TrunkExtension,
    AnalogGatewayExtension,
    CircuitExtension,
]
