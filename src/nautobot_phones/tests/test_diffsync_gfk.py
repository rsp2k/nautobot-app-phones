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
