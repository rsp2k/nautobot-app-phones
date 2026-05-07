"""Schema-sanity tests for the DiffSync model layer.

Each DiffSync model declares `_identifiers`, `_attributes`, `_model`. These
must stay aligned with the underlying Django model — drift between the two
shows up as silent sync errors (fields never compared, fields compared
that don't exist on the ORM side, identifiers that don't match unique
constraints).

Run via: ``nautobot-server test nautobot_phones.tests.test_diffsync_schema``
"""

from django.test import SimpleTestCase

from nautobot_phones.diffsync.models import (
    AnalogGatewayModel,
    AnalogPortModel,
    BusyLampFieldModel,
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
    DirectoryNumberModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneServiceUrlModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListModel,
    RoutePatternModel,
    SpeedDialModel,
    TranslationPatternModel,
    TrunkModel,
)


ALL_DIFFSYNC_MODELS = [
    AnalogGatewayModel,
    AnalogPortModel,
    BusyLampFieldModel,
    CSSPartitionMembershipModel,
    CallingSearchSpaceModel,
    DirectoryNumberModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneServiceUrlModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListModel,
    RoutePatternModel,
    SpeedDialModel,
    TranslationPatternModel,
    TrunkModel,
]


class TestDiffSyncSchemaSanity(SimpleTestCase):
    """Each DiffSync model must declare the framework's required class attrs."""

    def test_every_model_has_required_attrs(self) -> None:
        for cls in ALL_DIFFSYNC_MODELS:
            self.assertTrue(hasattr(cls, "_modelname"), f"{cls} missing _modelname")
            self.assertTrue(hasattr(cls, "_identifiers"), f"{cls} missing _identifiers")
            self.assertTrue(hasattr(cls, "_attributes"), f"{cls} missing _attributes")
            self.assertTrue(hasattr(cls, "_model"), f"{cls} missing _model")

    def test_identifiers_dont_overlap_attributes(self) -> None:
        """An identifier shouldn't ALSO be an attribute — that creates ambiguity
        about whether DiffSync should use it for matching or for comparing."""
        for cls in ALL_DIFFSYNC_MODELS:
            ids = set(cls._identifiers)
            attrs = set(cls._attributes)
            overlap = ids & attrs
            self.assertEqual(
                overlap, set(),
                f"{cls._modelname}: fields {overlap} declared as both identifier AND attribute",
            )

    def test_phone_uses_device_name_not_mac_for_identifier(self) -> None:
        """Phone uniqueness was changed from mac_address → device_name when
        we added softphone support (Jabber softphones have no MAC). Make
        sure that change is reflected here."""
        self.assertIn("device_name", PhoneModel._identifiers)
        self.assertNotIn("mac_address", PhoneModel._identifiers)
        # mac_address is now an attribute (optional), not an identifier
        self.assertIn("mac_address", PhoneModel._attributes)

    def test_button_models_share_phone_identifier_shape(self) -> None:
        """Line, SpeedDial, BusyLampField, PhoneServiceUrl all share the
        (phone__device_name, phone__phone_system__name, button_index)
        identifier shape — that's load-bearing for the four-array
        getPhone enrichment to diff cleanly."""
        button_models = [LineModel, SpeedDialModel, BusyLampFieldModel, PhoneServiceUrlModel]
        for cls in button_models:
            ids = cls._identifiers
            self.assertIn("phone__device_name", ids,
                          f"{cls._modelname} must identify by phone__device_name")
            self.assertIn("phone__phone_system__name", ids,
                          f"{cls._modelname} must identify by phone__phone_system__name")
            self.assertIn("button_index", ids,
                          f"{cls._modelname} must identify by button_index")
