"""Detail-view template extensions for nautobot-app-phones.

Adds a 'Vendor Extras' KeyValueTablePanel to the detail views of models
that carry the `vendor_extras` JSONField — DirectoryNumber, Phone, Trunk,
AnalogGateway. The panel renders the JSON as a clean two-column table.

Discovered by Nautobot via the module-level `template_extensions` list,
matched against the convention `nautobot_phones.template_content`.
"""

from nautobot.apps.ui import KeyValueTablePanel, TemplateExtension


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


template_extensions = [
    DirectoryNumberExtension,
    PhoneExtension,
    TrunkExtension,
    AnalogGatewayExtension,
]
