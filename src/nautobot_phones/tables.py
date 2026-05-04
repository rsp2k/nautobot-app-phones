"""django-tables2 Table classes for nautobot-app-phones list views.

Each PrimaryModel gets a Table that defines its column layout for the
list view. Conventions: leading ToggleColumn for bulk-action checkbox,
linked `name` column for navigation, trailing ButtonsColumn for
edit/delete actions.
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
        """Table meta — selects which fields render in the list view."""

        model = models.PhoneSystem
        fields = (
            "pk",
            "name",
            "vendor",
            "version",
            "hostname",
            "location",
            "last_synced_at",
            "actions",
        )
        default_columns = ("pk", "name", "vendor", "version", "hostname", "actions")
