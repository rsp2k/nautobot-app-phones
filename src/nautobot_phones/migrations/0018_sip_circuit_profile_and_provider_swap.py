"""Drop nautobot_phones.Carrier in favor of Nautobot's built-in circuits.Provider,
add SipCircuitProfile, and wire DIDBlock/DID/Trunk to circuits.Circuit.

Safe to apply destructively because no nautobot_phones.Carrier rows have ever
been created in any environment (greenfield app). If that ever changes, this
migration would silently drop carrier data — handle the data preservation in
a separate data migration BEFORE rerunning this one.
"""

import django.core.serializers.json
import django.db.models.deletion
import nautobot.core.models.fields
import nautobot.extras.models.mixins
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("circuits", "0022_circuittermination_cloud_network"),
        ("nautobot_phones", "0017_remove_huntlist_call_manager_group_and_more"),
    ]

    operations = [
        # ---- 1) DIDBlock: replace carrier FK with provider FK, add circuit FK.
        # The unique_together that references `carrier` has to be cleared FIRST,
        # otherwise RemoveField fails trying to drop a column still named in the
        # unique constraint.
        migrations.AlterUniqueTogether(
            name="didblock",
            unique_together=set(),
        ),
        migrations.RemoveField(
            model_name="didblock",
            name="carrier",
        ),
        migrations.AddField(
            model_name="didblock",
            name="provider",
            field=models.ForeignKey(
                help_text="The carrier (Nautobot circuits.Provider) that delivers this DID block.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="phone_did_blocks",
                to="circuits.provider",
            ),
        ),
        migrations.AddField(
            model_name="didblock",
            name="circuit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text=(
                    "Optional: the specific carrier circuit that delivers this block "
                    "(e.g. the SIP trunk these DIDs route over). Inventory rows can "
                    "exist before circuit assignment."
                ),
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="did_blocks",
                to="circuits.circuit",
            ),
        ),
        migrations.AlterModelOptions(
            name="didblock",
            options={
                "ordering": ("provider", "start_e164"),
                "verbose_name": "DID block",
                "verbose_name_plural": "DID blocks",
            },
        ),
        migrations.AlterUniqueTogether(
            name="didblock",
            unique_together={("start_e164", "end_e164", "provider")},
        ),
        # ---- 2) DID: add circuit FK
        migrations.AddField(
            model_name="did",
            name="circuit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text=(
                    "Optional: the specific carrier circuit delivering this DID. "
                    "Usually inherited from block.circuit; set directly only for "
                    "one-off DIDs that aren't part of any block."
                ),
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="dids",
                to="circuits.circuit",
            ),
        ),
        # ---- 3) Trunk: add circuit FK
        migrations.AddField(
            model_name="trunk",
            name="circuit",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text=(
                    "Optional: the carrier circuit this PBX-side trunk terminates. "
                    "Multiple Trunks (e.g. active/standby SBC pair) may point at "
                    "the same Circuit."
                ),
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="phone_trunks",
                to="circuits.circuit",
            ),
        ),
        # ---- 4) Drop the Carrier model itself
        migrations.DeleteModel(
            name="Carrier",
        ),
        # ---- 5) Create SipCircuitProfile (OneToOne to circuits.Circuit)
        migrations.CreateModel(
            name="SipCircuitProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("_custom_field_data", models.JSONField(blank=True, default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ("pilot_e164", models.CharField(
                    blank=True,
                    max_length=32,
                    help_text=(
                        "Main/pilot number, digits only. Often the OLI/CLID for outbound "
                        "calls (e.g. '2082396520' for the SparkLight Bingham trunk)."
                    ),
                )),
                ("sip_sessions", models.PositiveIntegerField(
                    help_text=(
                        "Concurrent SIP session ceiling sold by the carrier. Hard cap on "
                        "simultaneous calls across the entire DID pool routed via this circuit."
                    ),
                )),
                ("oli_clid_policy", models.CharField(
                    blank=True,
                    max_length=128,
                    help_text=(
                        "Outbound CLID policy (e.g. 'Public, set to Pilot', "
                        "'Pass-through DID', 'Anonymous')."
                    ),
                )),
                ("tech_support", models.CharField(
                    blank=True,
                    max_length=255,
                    help_text=(
                        "Carrier tech support contact, as printed on the cut sheet "
                        "(e.g. '1-877-469-2251 option 2'). Free text — phone, email, "
                        "or URL all welcome."
                    ),
                )),
                ("cut_sheet_received_date", models.DateField(
                    blank=True,
                    null=True,
                    help_text=(
                        "Date the carrier delivered the cut sheet / config. Distinct from "
                        "circuit install_date; useful for tracking which document version "
                        "drove this configuration."
                    ),
                )),
                ("source_doc", models.CharField(
                    blank=True,
                    max_length=255,
                    help_text=(
                        "Filename or reference for the source cut sheet "
                        "(e.g. 'SIP Cut Sheet Bingham 1.xlsx')."
                    ),
                )),
                ("sensitivity", models.CharField(
                    blank=True,
                    max_length=32,
                    help_text="Sensitivity tag (e.g. 'internal', 'public', 'confidential').",
                )),
                ("vendor_extras", models.JSONField(
                    blank=True,
                    default=dict,
                    help_text="Carrier-specific fields not modeled as columns. Adapter-driven.",
                )),
                ("circuit", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sip_profile",
                    to="circuits.circuit",
                    help_text="The carrier circuit this profile extends.",
                )),
                ("tags", nautobot.core.models.fields.TagsField(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={
                "verbose_name": "SIP circuit profile",
                "verbose_name_plural": "SIP circuit profiles",
                "ordering": ("circuit",),
            },
            bases=(
                nautobot.extras.models.mixins.DataComplianceModelMixin,
                nautobot.extras.models.mixins.DynamicGroupMixin,
                nautobot.extras.models.mixins.NotesMixin,
                models.Model,
            ),
        ),
    ]
