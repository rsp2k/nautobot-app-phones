"""Django forms for nautobot-app-phones create/edit views and filter UIs.

Each PrimaryModel typically gets two forms: a `XForm` (NautobotModelForm)
for create/edit, and a `XFilterForm` (NautobotFilterForm) for the list-
view filter sidebar.
"""

from django import forms
from nautobot.apps.forms import NautobotFilterForm, NautobotModelForm

from nautobot_phones import models
from nautobot_phones.choices import VendorChoices


class PhoneSystemForm(NautobotModelForm):
    """Create/edit form for PhoneSystem."""

    class Meta:
        """Form meta."""

        model = models.PhoneSystem
        fields = (
            "name",
            "vendor",
            "version",
            "hostname",
            "secrets_group",
            "location",
            "delete_policy",
            "tags",
        )


class PhoneSystemFilterForm(NautobotFilterForm):
    """Filter sidebar form for PhoneSystem list view."""

    model = models.PhoneSystem
    field_order = ("q", "name", "vendor", "version", "hostname", "location")

    q = forms.CharField(required=False, label="Search")
    vendor = forms.MultipleChoiceField(choices=VendorChoices, required=False)
