"""Tests for the Phase 6 per-model ``delete_policy`` dispatch.

Verifies the three policy actions on the ``PolicyAwareNautobotModel``
base class:

* **delete** (default): hard ORM delete — vanilla NautobotModel behavior.
  Empty / missing policy resolves here, so back-compat is preserved.
* **ignore**: log + skip the ORM delete; record stays in Nautobot.
* **flag**: preserve the record + add ``phones-orphaned`` Tag + write
  ``_orphaned_at`` ISO-8601 timestamp into ``vendor_extras``.

Each action is exercised via a unit-level path (call ``.delete()`` on
a DiffSync model bound to a mock adapter carrying the policy dict)
plus a focused ORM verification (queried after).
"""

from datetime import datetime
from unittest.mock import MagicMock

from django.test import TestCase
from nautobot.extras.models import Tag

from nautobot_phones import models
from nautobot_phones.diffsync.models.base import PhoneSystemModel, TrunkModel
from nautobot_phones.diffsync.models.policy import (
    ORPHANED_TAG_NAME,
    DeletePolicy,
    PolicyAwareNautobotModel,
)


def _StubAdapter(delete_policy=None, job=None):
    """Build a real ``PhonesNautobotAdapter`` (no .load()) carrying the
    given delete_policy.

    We can't substitute a plain diffsync.Adapter — the super().delete()
    path calls ``self.adapter.get_from_orm_cache`` which only exists on
    ``BaseNautobotAdapter``. Using the real adapter is cheap as long as
    we skip the heavy load() walk.
    """
    from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
    return PhonesNautobotAdapter(job=job, delete_policy=delete_policy or {})


class DeletePolicyActionTests(TestCase):
    """Each policy action triggers the right branch in ``delete()``."""

    def setUp(self) -> None:
        """Create a Trunk record to exercise delete() against.

        Trunk is a PrimaryModel (has ``tags``) AND has ``vendor_extras``
        — the model that gets the most out of the flag action. Other
        BaseModel-derived diffsync models exercise the same code with
        slightly different surfaces (no tags, no vendor_extras).
        """
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-CCM", vendor="cisco_ucm",
            version="15.0", hostname="ccm.example.com",
        )
        self.trunk = models.Trunk.objects.create(
            name="OUTBOUND-SIP", phone_system=self.ps, trunk_type="sip",
            vendor_extras={"existing": "value"},  # baseline to confirm we don't clobber
        )

    def _bind_trunk_model(self, *, policy: dict) -> TrunkModel:
        """Build a TrunkModel diffsync instance bound to an adapter
        carrying ``policy`` and seeded with the existing ORM record's pk."""
        adapter = _StubAdapter(delete_policy=policy)
        record = TrunkModel(
            name="OUTBOUND-SIP",
            phone_system__name="LAB-CCM",
            trunk_type="sip",
            destination_address="",
            destination_port=None,
            vendor_extras={"existing": "value"},
        )
        record.pk = self.trunk.pk
        adapter.add(record)
        return record

    def test_default_action_is_delete(self) -> None:
        """Empty policy → ORM record is hard-deleted (vanilla behavior)."""
        record = self._bind_trunk_model(policy={})
        record.delete()
        self.assertFalse(
            models.Trunk.objects.filter(pk=self.trunk.pk).exists(),
            "Trunk should be deleted under the default 'delete' policy",
        )

    def test_explicit_delete_action(self) -> None:
        """Explicit ``{"trunk": "delete"}`` matches the empty-policy default."""
        record = self._bind_trunk_model(policy={"trunk": "delete"})
        record.delete()
        self.assertFalse(models.Trunk.objects.filter(pk=self.trunk.pk).exists())

    def test_ignore_action_preserves_record(self) -> None:
        """``"ignore"`` leaves the ORM record untouched but tells DiffSync
        the record is resolved from its in-memory store."""
        record = self._bind_trunk_model(policy={"trunk": "ignore"})
        record.delete()
        self.assertTrue(
            models.Trunk.objects.filter(pk=self.trunk.pk).exists(),
            "Trunk should be preserved under the 'ignore' policy",
        )
        # vendor_extras untouched — no flag-style markers leaked through.
        trunk = models.Trunk.objects.get(pk=self.trunk.pk)
        self.assertNotIn("_orphaned_at", trunk.vendor_extras)

    def test_flag_action_preserves_and_tags(self) -> None:
        """``"flag"`` preserves the record + adds the orphaned Tag + writes
        ``_orphaned_at`` ISO timestamp into vendor_extras."""
        record = self._bind_trunk_model(policy={"trunk": "flag"})
        record.delete()
        trunk = models.Trunk.objects.get(pk=self.trunk.pk)
        # Tag attached.
        self.assertTrue(
            trunk.tags.filter(name=ORPHANED_TAG_NAME).exists(),
            "Trunk should carry the phones-orphaned tag after flag",
        )
        # Timestamp written into vendor_extras (and existing keys preserved).
        self.assertIn("_orphaned_at", trunk.vendor_extras)
        self.assertEqual(trunk.vendor_extras["existing"], "value")
        # Timestamp is a parseable ISO-8601 string.
        try:
            datetime.fromisoformat(trunk.vendor_extras["_orphaned_at"])
        except ValueError as e:
            self.fail(f"_orphaned_at is not parseable ISO-8601: {e}")

    def test_flag_action_is_idempotent(self) -> None:
        """A second flag pass on an already-flagged record keeps the
        ORIGINAL ``_orphaned_at`` — don't bump on every sync."""
        record = self._bind_trunk_model(policy={"trunk": "flag"})
        record.delete()
        original_ts = models.Trunk.objects.get(
            pk=self.trunk.pk).vendor_extras["_orphaned_at"]

        # Second pass — rebuild record (DiffSync removed it from store first time).
        record2 = self._bind_trunk_model(policy={"trunk": "flag"})
        record2.delete()
        second_ts = models.Trunk.objects.get(
            pk=self.trunk.pk).vendor_extras["_orphaned_at"]
        self.assertEqual(original_ts, second_ts,
                         "_orphaned_at should not change on re-flag")

    def test_unknown_action_falls_back_to_delete(self) -> None:
        """A typo'd action ("delet" / "fag" / "FLAG" / etc.) falls back to
        delete with a warning log — better to delete than silently leave
        records when the operator clearly intended SOMETHING non-default."""
        record = self._bind_trunk_model(policy={"trunk": "fag"})
        record.delete()
        self.assertFalse(models.Trunk.objects.filter(pk=self.trunk.pk).exists())

    def test_other_models_unaffected_by_policy_on_trunk(self) -> None:
        """Policy is per-model: a flag policy on ``trunk`` doesn't affect
        a DirectoryNumber delete in the same run."""
        partition = models.Partition.objects.create(name="PT", phone_system=self.ps)
        dn = models.DirectoryNumber.objects.create(
            extension="1001", partition=partition, phone_system=self.ps,
        )
        # Bind a DN diffsync record with policy that only mentions trunk.
        from nautobot_phones.diffsync.models.base import DirectoryNumberModel
        adapter = _StubAdapter(delete_policy={"trunk": "flag"})
        dn_record = DirectoryNumberModel(
            extension="1001",
            partition__name="PT",
            partition__phone_system__name="LAB-CCM",
            alerting_name="", voicemail_profile__name=None, vendor_extras={},
        )
        dn_record.pk = dn.pk
        adapter.add(dn_record)
        dn_record.delete()
        # DN was deleted (no policy entry for "directory_number" → default).
        self.assertFalse(
            models.DirectoryNumber.objects.filter(pk=dn.pk).exists(),
            "DirectoryNumber should follow default delete policy even when "
            "the policy dict mentions Trunk",
        )


class OrphanedTagBootstrappingTests(TestCase):
    """The ``phones-orphaned`` Tag is lazy-created on first flag."""

    def setUp(self) -> None:
        # Ensure tag doesn't pre-exist.
        Tag.objects.filter(name=ORPHANED_TAG_NAME).delete()
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-CCM", vendor="cisco_ucm",
            version="15.0", hostname="ccm.example.com",
        )

    def test_tag_created_on_first_flag(self) -> None:
        """First flag operation creates the Tag with the right ContentTypes."""
        from django.contrib.contenttypes.models import ContentType
        trunk = models.Trunk.objects.create(
            name="T1", phone_system=self.ps, trunk_type="sip",
        )
        adapter = _StubAdapter(delete_policy={"trunk": "flag"})
        record = TrunkModel(
            name="T1", phone_system__name="LAB-CCM", trunk_type="sip",
            destination_address="", destination_port=None, vendor_extras={},
        )
        record.pk = trunk.pk
        adapter.add(record)
        record.delete()
        tag = Tag.objects.get(name=ORPHANED_TAG_NAME)
        self.assertIn(
            ContentType.objects.get_for_model(models.Trunk),
            tag.content_types.all(),
            "Tag's content_types should include the model class it was first applied to",
        )

    def test_tag_content_types_extended_by_second_model_flag(self) -> None:
        """A second flag against a different model class adds that
        model's ContentType to the Tag without recreating the tag."""
        from django.contrib.contenttypes.models import ContentType
        # First flag — Trunk
        trunk = models.Trunk.objects.create(
            name="T1", phone_system=self.ps, trunk_type="sip",
        )
        adapter = _StubAdapter(delete_policy={"trunk": "flag"})
        record = TrunkModel(
            name="T1", phone_system__name="LAB-CCM", trunk_type="sip",
            destination_address="", destination_port=None, vendor_extras={},
        )
        record.pk = trunk.pk
        adapter.add(record)
        record.delete()
        tag = Tag.objects.get(name=ORPHANED_TAG_NAME)
        self.assertEqual(tag.content_types.count(), 1)

        # Second flag — PhoneSystem itself (different content type)
        adapter2 = _StubAdapter(delete_policy={"phone_system": "flag"})
        ps_record = PhoneSystemModel(
            name="LAB-CCM", vendor="cisco_ucm", version="15.0",
            hostname="ccm.example.com",
        )
        ps_record.pk = self.ps.pk
        adapter2.add(ps_record)
        ps_record.delete()
        tag.refresh_from_db()
        # Tag is the same one (lazy get_or_create), but now spans two CTs.
        self.assertEqual(Tag.objects.filter(name=ORPHANED_TAG_NAME).count(), 1)
        self.assertEqual(tag.content_types.count(), 2)
        cts = set(tag.content_types.values_list("model", flat=True))
        self.assertEqual(cts, {"trunk", "phonesystem"})


class DeletePolicyConstantsTests(TestCase):
    """Smoke tests for the ``DeletePolicy`` constants."""

    def test_all_actions_in_frozenset(self) -> None:
        self.assertEqual(
            DeletePolicy.ALL,
            frozenset({"delete", "ignore", "flag"}),
        )

    def test_action_constants_are_strings(self) -> None:
        self.assertEqual(DeletePolicy.DELETE, "delete")
        self.assertEqual(DeletePolicy.IGNORE, "ignore")
        self.assertEqual(DeletePolicy.FLAG, "flag")


class AdapterDeletePolicyAttributeTests(TestCase):
    """``PhonesNautobotAdapter`` accepts and stores the ``delete_policy`` kwarg."""

    def test_default_is_empty_dict(self) -> None:
        from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
        adapter = PhonesNautobotAdapter(job=None)
        self.assertEqual(adapter.delete_policy, {})

    def test_passed_policy_stored_on_adapter(self) -> None:
        from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
        adapter = PhonesNautobotAdapter(
            job=None,
            delete_policy={"phone": "flag", "trunk": "ignore"},
        )
        self.assertEqual(adapter.delete_policy,
                         {"phone": "flag", "trunk": "ignore"})

    def test_none_policy_becomes_empty_dict(self) -> None:
        """Defensive: ``delete_policy=None`` (e.g. from a PhoneSystem
        with the field never set) becomes an empty dict, not ``None`` —
        downstream ``.get()`` calls don't blow up."""
        from nautobot_phones.diffsync.adapters.nautobot import PhonesNautobotAdapter
        adapter = PhonesNautobotAdapter(job=None, delete_policy=None)
        self.assertEqual(adapter.delete_policy, {})
