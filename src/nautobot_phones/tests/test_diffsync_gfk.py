"""Tests for the GFK-aware DiffSync base class.

Validates the resolve-then-delegate logic in ``GFKNautobotModel`` without
hitting the ORM: the resolver only depends on the ``_gfk_targets`` map
and a ``ContentType`` lookup. We patch ``ContentType.objects.get`` and
the target model queryset to keep tests pure.
"""

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

from django.test import SimpleTestCase
from diffsync.exceptions import ObjectCrudException

from nautobot_phones.diffsync.models.gfk import GFKNautobotModel


class _DummyGFKModel(GFKNautobotModel):
    """Minimal subclass for testing the resolver in isolation."""

    _gfk_targets = {
        "trunk": ("nautobot_phones", "trunk"),
        "analoggateway": ("nautobot_phones", "analoggateway"),
    }
    _gfk_scope_from = "parent__phone_system__name"


class TestResolveGFKTarget(SimpleTestCase):
    """``_resolve_gfk_target`` returns (ContentType, target_id) tuples."""

    _FAKE_UUID = UUID("11111111-2222-3333-4444-555555555555")

    def _build_ct_patch(self) -> Any:
        """Make ContentType.objects.get return a mock whose model_class()
        returns a fake QuerySet manager. The fake manager's ``.get()``
        returns an object with ``.id`` set to a known UUID."""
        target_obj = MagicMock()
        target_obj.id = self._FAKE_UUID

        fake_model_class = MagicMock()
        fake_model_class.__name__ = "Trunk"
        fake_model_class.objects.get = MagicMock(return_value=target_obj)
        # Wire DoesNotExist / MultipleObjectsReturned as accessible exception
        # types on the fake class.
        fake_model_class.DoesNotExist = type("DoesNotExist", (Exception,), {})
        fake_model_class.MultipleObjectsReturned = type("MultipleObjectsReturned", (Exception,), {})

        ct = MagicMock()
        ct.model_class = MagicMock(return_value=fake_model_class)
        return ct, fake_model_class, target_obj

    def test_happy_path_returns_ct_and_id(self) -> None:
        ct, fake_model_class, _ = self._build_ct_patch()
        with patch(
            "nautobot_phones.diffsync.models.gfk.ContentType.objects.get",
            return_value=ct,
        ):
            result_ct, result_id = _DummyGFKModel._resolve_gfk_target(
                "trunk", "SIP-TRK-1", {"parent__phone_system__name": "LAB"},
            )
        self.assertIs(result_ct, ct)
        self.assertEqual(result_id, self._FAKE_UUID)
        # Confirm the scoped lookup was applied.
        fake_model_class.objects.get.assert_called_once_with(
            name="SIP-TRK-1", phone_system__name="LAB",
        )

    def test_unscoped_lookup_when_no_scope_value(self) -> None:
        """If the scope identifier isn't in parameters, the lookup is by
        name only — vendor-agnostic catch for cases where the parent has
        no phone_system constraint."""
        ct, fake_model_class, _ = self._build_ct_patch()
        with patch(
            "nautobot_phones.diffsync.models.gfk.ContentType.objects.get",
            return_value=ct,
        ):
            _DummyGFKModel._resolve_gfk_target("trunk", "T1", {})
        fake_model_class.objects.get.assert_called_once_with(name="T1")

    def test_unknown_kind_raises_objectcrudexception(self) -> None:
        """A target_kind not in _gfk_targets is rejected before any DB
        lookup happens."""
        with self.assertRaises(ObjectCrudException) as ctx:
            _DummyGFKModel._resolve_gfk_target("phone", "DOES-NOT-MATTER", {})
        self.assertIn("Unknown GFK target kind", str(ctx.exception))

    def test_target_doesnotexist_raises_objectcrudexception(self) -> None:
        ct, fake_model_class, _ = self._build_ct_patch()
        fake_model_class.objects.get.side_effect = fake_model_class.DoesNotExist()
        with patch(
            "nautobot_phones.diffsync.models.gfk.ContentType.objects.get",
            return_value=ct,
        ):
            with self.assertRaises(ObjectCrudException) as cm:
                _DummyGFKModel._resolve_gfk_target("trunk", "GHOST", {})
        self.assertIn("GFK target lookup failed", str(cm.exception))

    def test_target_ambiguous_raises_objectcrudexception(self) -> None:
        ct, fake_model_class, _ = self._build_ct_patch()
        fake_model_class.objects.get.side_effect = fake_model_class.MultipleObjectsReturned()
        with patch(
            "nautobot_phones.diffsync.models.gfk.ContentType.objects.get",
            return_value=ct,
        ):
            with self.assertRaises(ObjectCrudException) as cm:
                _DummyGFKModel._resolve_gfk_target("trunk", "AMBIG", {})
        self.assertIn("ambiguous", str(cm.exception))


# ---------------------------------------------------------------------------
# Per-kind lookup overrides (_gfk_lookups)
# ---------------------------------------------------------------------------


class _DNStyleGFKModel(GFKNautobotModel):
    """Subclass with two kinds where one uses a composite-key lookup
    (mirrors the real DIDAssignment shape)."""

    _gfk_targets = {
        "directorynumber": ("nautobot_phones", "directorynumber"),
        "trunk": ("nautobot_phones", "trunk"),
    }
    _gfk_lookups = {
        "directorynumber": lambda name, params: {
            "extension": name,
            "partition__name": params.get("target_partition__name"),
            "partition__phone_system__name": params.get("target_phone_system__name"),
        },
        # trunk intentionally omitted — falls back to name-based default.
    }
    _gfk_scope_from = "target_phone_system__name"


class TestPerKindLookups(SimpleTestCase):
    """``_gfk_lookups[kind]`` callable wins over the default name-based lookup."""

    _FAKE_UUID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    def _patch_ct(self, model_name: str = "Trunk") -> tuple[Any, Any]:
        target_obj = MagicMock()
        target_obj.id = self._FAKE_UUID

        fake_model_class = MagicMock()
        fake_model_class.__name__ = model_name
        fake_model_class.objects.get = MagicMock(return_value=target_obj)
        fake_model_class.DoesNotExist = type("DoesNotExist", (Exception,), {})
        fake_model_class.MultipleObjectsReturned = type("MultipleObjectsReturned", (Exception,), {})

        ct = MagicMock()
        ct.model_class = MagicMock(return_value=fake_model_class)
        return ct, fake_model_class

    def test_dn_uses_composite_lookup(self) -> None:
        """A kind in _gfk_lookups uses the callable's result, not the
        default ``{name: target_name}`` shape."""
        ct, fake_model_class = self._patch_ct("DirectoryNumber")
        params = {
            "target_partition__name": "Internal-PT",
            "target_phone_system__name": "LAB-CCM",
        }
        with patch(
            "nautobot_phones.diffsync.models.gfk.ContentType.objects.get",
            return_value=ct,
        ):
            _DNStyleGFKModel._resolve_gfk_target("directorynumber", "1001", params)
        fake_model_class.objects.get.assert_called_once_with(
            extension="1001",
            partition__name="Internal-PT",
            partition__phone_system__name="LAB-CCM",
        )

    def test_trunk_falls_back_to_default_name_lookup(self) -> None:
        """A kind NOT in _gfk_lookups uses the default name+scope path —
        backward compat with RouteGroupMember semantics."""
        ct, fake_model_class = self._patch_ct("Trunk")
        params = {"target_phone_system__name": "LAB-CCM"}
        with patch(
            "nautobot_phones.diffsync.models.gfk.ContentType.objects.get",
            return_value=ct,
        ):
            _DNStyleGFKModel._resolve_gfk_target("trunk", "SIP-TRK", params)
        fake_model_class.objects.get.assert_called_once_with(
            name="SIP-TRK", phone_system__name="LAB-CCM",
        )


# ---------------------------------------------------------------------------
# Read-path virtual-field extraction (_gfk_reads + _extract_gfk_virtual_field)
# ---------------------------------------------------------------------------


class _ReadStyleGFKModel(GFKNautobotModel):
    """Subclass exercising the read-path extractor map."""

    _gfk_targets = {
        "directorynumber": ("nautobot_phones", "directorynumber"),
        "trunk": ("nautobot_phones", "trunk"),
    }
    _gfk_reads = {
        "directorynumber": lambda target: {
            "target_name": target.extension,
            "target_partition__name": target.partition.name,
            "target_phone_system__name": target.partition.phone_system.name,
        },
        "trunk": lambda target: {
            "target_name": target.name,
            "target_partition__name": "",
            "target_phone_system__name": target.phone_system.name,
        },
    }


class TestExtractGFKVirtualField(SimpleTestCase):
    """``_extract_gfk_virtual_field`` pulls virtual values off the ORM target."""

    def _make_dn_object(self) -> Any:
        """Mock ORM DIDAssignment whose target is a DirectoryNumber."""
        dn = MagicMock()
        dn.extension = "1001"
        dn.partition.name = "Internal-PT"
        dn.partition.phone_system.name = "LAB-CCM"

        db_obj = MagicMock()
        db_obj.target_type.model = "directorynumber"
        db_obj.target = dn
        return db_obj

    def _make_trunk_object(self) -> Any:
        trunk = MagicMock()
        trunk.name = "SIP-OUTBOUND"
        trunk.phone_system.name = "LAB-CCM"

        db_obj = MagicMock()
        db_obj.target_type.model = "trunk"
        db_obj.target = trunk
        return db_obj

    def test_target_kind_extracted_from_content_type(self) -> None:
        db_obj = self._make_dn_object()
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_kind"),
            "directorynumber",
        )

    def test_dn_target_extracts_extension_and_partition(self) -> None:
        db_obj = self._make_dn_object()
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_name"),
            "1001",
        )
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_partition__name"),
            "Internal-PT",
        )
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_phone_system__name"),
            "LAB-CCM",
        )

    def test_trunk_target_extracts_name_and_phone_system(self) -> None:
        db_obj = self._make_trunk_object()
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_name"),
            "SIP-OUTBOUND",
        )
        # Trunks have no partition — reader returns empty string.
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_partition__name"),
            "",
        )
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_phone_system__name"),
            "LAB-CCM",
        )

    def test_null_target_returns_empty_string(self) -> None:
        """Defensive: a row with a stale GFK (target_id pointing at a
        deleted object) returns empty rather than crashing the adapter."""
        db_obj = MagicMock()
        db_obj.target_type.model = "trunk"
        db_obj.target = None
        self.assertEqual(
            _ReadStyleGFKModel._extract_gfk_virtual_field(db_obj, "target_name"),
            "",
        )

    def test_unmapped_kind_falls_back_to_name_attr(self) -> None:
        """Subclasses with no _gfk_reads entry for a kind still extract
        ``target.name`` when present — preserves RouteGroupMember
        compatibility (which doesn't define _gfk_reads)."""

        class _SimpleModel(GFKNautobotModel):
            _gfk_targets = {"trunk": ("nautobot_phones", "trunk")}
            # _gfk_reads intentionally empty.

        trunk = MagicMock()
        trunk.name = "FALLBACK-T"
        db_obj = MagicMock()
        db_obj.target_type.model = "trunk"
        db_obj.target = trunk
        self.assertEqual(
            _SimpleModel._extract_gfk_virtual_field(db_obj, "target_name"),
            "FALLBACK-T",
        )


# ---------------------------------------------------------------------------
# DIDAssignmentModel concrete subclass — schema + lambda smoke tests
# ---------------------------------------------------------------------------


class TestDIDAssignmentModelSchema(SimpleTestCase):
    """The concrete ``DIDAssignmentModel`` is correctly configured."""

    def test_imports_and_metadata(self) -> None:
        """Model is exported, has the expected identifier/attribute schema."""
        from nautobot_phones.diffsync.models import DIDAssignmentModel
        self.assertEqual(DIDAssignmentModel._modelname, "did_assignment")
        self.assertEqual(DIDAssignmentModel._identifiers, ("did__e164",))
        self.assertEqual(set(DIDAssignmentModel._attributes), {
            "target_kind", "target_name",
            "target_partition__name", "target_phone_system__name",
        })

    def test_dn_lookup_callable_shape(self) -> None:
        """Calling the registered DN lookup with realistic params produces
        the right queryset filter."""
        from nautobot_phones.diffsync.models import DIDAssignmentModel
        f = DIDAssignmentModel._gfk_lookups["directorynumber"](
            "1001",
            {"target_partition__name": "Internal-PT",
             "target_phone_system__name": "LAB-CCM"},
        )
        self.assertEqual(f, {
            "extension": "1001",
            "partition__name": "Internal-PT",
            "partition__phone_system__name": "LAB-CCM",
        })

    def test_trunk_lookup_callable_shape(self) -> None:
        from nautobot_phones.diffsync.models import DIDAssignmentModel
        f = DIDAssignmentModel._gfk_lookups["trunk"](
            "SIP-OUT",
            {"target_phone_system__name": "LAB-CCM"},
        )
        self.assertEqual(f, {"name": "SIP-OUT", "phone_system__name": "LAB-CCM"})

    def test_dn_read_callable_shape(self) -> None:
        """The DN read extractor pulls ``extension`` (not ``name``) and the
        nested partition/phone_system chain."""
        from nautobot_phones.diffsync.models import DIDAssignmentModel
        dn = MagicMock()
        dn.extension = "1001"
        dn.partition.name = "Internal-PT"
        dn.partition.phone_system.name = "LAB-CCM"
        out = DIDAssignmentModel._gfk_reads["directorynumber"](dn)
        self.assertEqual(out, {
            "target_name": "1001",
            "target_partition__name": "Internal-PT",
            "target_phone_system__name": "LAB-CCM",
        })

    def test_trunk_read_callable_shape(self) -> None:
        from nautobot_phones.diffsync.models import DIDAssignmentModel
        trunk = MagicMock()
        trunk.name = "SIP-OUT"
        trunk.phone_system.name = "LAB-CCM"
        out = DIDAssignmentModel._gfk_reads["trunk"](trunk)
        self.assertEqual(out, {
            "target_name": "SIP-OUT",
            "target_partition__name": "",
            "target_phone_system__name": "LAB-CCM",
        })
