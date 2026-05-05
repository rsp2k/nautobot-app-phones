"""Add CustomFields on dcim.Interface for voice function + physical connector.

Nautobot's core ``InterfaceTypeChoices`` doesn't include FXS / FXO (function)
or RJ-11 / RJ-21 (connector). We surface them as CustomFields on Interface
so analog voice ports synced from CCM-side gateways carry semantically
meaningful metadata in DCIM. They're orthogonal facts (you can have an
FXS port terminated as RJ-11 individual jack on a NIM-2FXS, or as RJ-21
50-pin Amphenol on an SM-X-72FXS-SCCP), so they're modeled as two
separate fields rather than a combined enum.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    """Create the CustomFields + their choice values."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    CustomFieldChoice = apps.get_model("extras", "CustomFieldChoice")

    iface_ct = ContentType.objects.get(app_label="dcim", model="interface")

    voice_fn, _ = CustomField.objects.update_or_create(
        key="voice_function",
        defaults={
            "type": "select",
            "label": "Voice Function",
            "description": (
                "Voice port role: FXS provides a POTS line to an analog phone; "
                "FXO terminates a POTS line from the telco/PSTN."
            ),
            "grouping": "Voice",
            "weight": 1100,
            "advanced_ui": False,
        },
    )
    voice_fn.content_types.add(iface_ct)
    for value, weight in (("fxs", 100), ("fxo", 200)):
        CustomFieldChoice.objects.update_or_create(
            custom_field=voice_fn, value=value,
            defaults={"weight": weight},
        )

    phys_conn, _ = CustomField.objects.update_or_create(
        key="physical_connector",
        defaults={
            "type": "select",
            "label": "Physical Connector",
            "description": (
                "Physical wiring at the chassis: RJ-11 individual jack (low-density "
                "modules — 2-4 ports), RJ-21 50-pin Amphenol (high-density 24-72 "
                "port modules)."
            ),
            "grouping": "Voice",
            "weight": 1110,
            "advanced_ui": False,
        },
    )
    phys_conn.content_types.add(iface_ct)
    for value, weight in (("rj-11", 100), ("rj-21", 200)):
        CustomFieldChoice.objects.update_or_create(
            custom_field=phys_conn, value=value,
            defaults={"weight": weight},
        )


def backwards(apps, schema_editor):
    """Remove the CustomFields (and their choices via cascade)."""
    CustomField = apps.get_model("extras", "CustomField")
    CustomField.objects.filter(key__in=["voice_function", "physical_connector"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_phones", "0012_phone_active_load_phone_inactive_load_and_more"),
        ("extras", "0001_initial_part_1"),
        ("dcim", "0001_initial_part_1"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
