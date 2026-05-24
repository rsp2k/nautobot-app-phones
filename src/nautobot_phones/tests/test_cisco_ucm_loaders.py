"""Focused unit tests for CCM adapter loaders not already covered by
``test_cisco_ucm_adapter.py``.

That file covers RouteList through-table + RouteGroupMember GFK
loaders. This file fills in the rest: partitions, CSSes, directory
numbers, trunks, route patterns, translation patterns, device profiles,
voicemail profiles, call pickup groups, route groups, hunt subsystem,
and the phones/lines dispatcher.

Reuses the mocked-client pattern from the sibling file: each test
opts in to non-empty data for the specific surface it asserts on.
"""

from typing import Any
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter


def _make_phone_system_stub(name: str = "LAB-CCM") -> Any:
    """Build a stand-in PhoneSystem object without touching the ORM."""
    ps = MagicMock()
    ps.name = name
    ps.vendor = "cisco_ucm"
    ps.version = "15.0"
    ps.hostname = "ccm-pub.example.com"
    return ps


def _make_client() -> Any:
    """AXLClient mock with every collection empty by default — tests
    opt in to non-empty data on the specific surface they exercise.

    The dispatch tables here cover everything the CCM adapter's
    ``load()`` walks. New loaders should also add entries here so
    tests don't accidentally fail with ``AttributeError`` on a
    method that wasn't pre-stubbed.
    """
    client = MagicMock()
    # ``client.list_X`` methods — direct collection iterators.
    for name in (
        "list_route_lists", "list_route_groups", "list_route_partitions",
        "list_css", "list_lines", "list_phones", "list_sip_trunks",
        "list_route_patterns", "list_translation_patterns",
        "list_gateways",
    ):
        setattr(client, name, MagicMock(return_value=[]))
    client._list = MagicMock(return_value=[])

    client._service = MagicMock()
    # Per-record getX enrichment — empty zeep-wrapped defaults.
    for name in (
        "getRouteList", "getRouteGroup", "getHuntList", "getLineGroup",
        "getGateway", "getDevicePool", "getVoiceMailProfile",
        "getCallPickupGroup", "getRoutePattern", "getCss",
    ):
        setattr(client._service, name, MagicMock(return_value={"return": {name[3].lower() + name[4:]: None}}))

    # List* via _service — used by device_profiles, voicemail, pickup.
    for name in ("listDevicePool", "listVoiceMailProfile",
                 "listCallPickupGroup", "listLine", "listHuntPilot",
                 "listHuntList", "listLineGroup"):
        setattr(client._service, name, MagicMock(return_value={"return": {}}))
    return client


def _run(client: Any) -> CUCMSourceAdapter:
    """Build + load the adapter."""
    adapter = CUCMSourceAdapter(
        client=client,
        phone_system_record=_make_phone_system_stub(),
        enrich_phone_lines=False,
        enrich_phone_ip=False,
    )
    adapter.load()
    return adapter


# ---------------------------------------------------------------------------
# _load_partitions
# ---------------------------------------------------------------------------


class TestLoadPartitions(SimpleTestCase):
    """``_load_partitions`` emits one Partition per AXL row + the synthetic
    NULL placeholder."""

    def test_emits_partitions_from_axl(self) -> None:
        client = _make_client()
        client.list_route_partitions = MagicMock(return_value=[
            {"name": "Internal-PT", "description": "Internal extensions"},
            {"name": "PSTN-PT", "description": "Outbound"},
        ])
        adapter = _run(client)
        names = sorted(p.name for p in adapter.get_all("partition"))
        # Includes the synthetic NULL placeholder for partition-less DNs.
        self.assertIn("Internal-PT", names)
        self.assertIn("PSTN-PT", names)
        self.assertIn(adapter.NULL_PARTITION_NAME, names)

    def test_null_partition_emitted_even_with_no_axl_partitions(self) -> None:
        """Empty AXL → still emits the NULL placeholder so partition-less
        DNs / patterns have something to point at."""
        adapter = _run(_make_client())
        names = [p.name for p in adapter.get_all("partition")]
        self.assertEqual(names, [adapter.NULL_PARTITION_NAME])


# ---------------------------------------------------------------------------
# _load_calling_search_spaces + getCss enrichment for memberships
# ---------------------------------------------------------------------------


class TestLoadCallingSearchSpaces(SimpleTestCase):
    """CSSes are loaded via listCss; partition memberships via getCss."""

    def _client_with_one_css(self, members: list[dict]) -> Any:
        client = _make_client()
        client.list_css = MagicMock(return_value=[{"name": "Internal-CSS"}])
        # ``_load_calling_search_spaces`` uses
        # ``getattr(self.client._service.getCss(...), "return").css`` —
        # a real attribute walk, not dict subscript. So the mock has to
        # be a MagicMock with a real ``.return.css`` attribute path.
        css_obj = MagicMock()
        css_obj.name = "Internal-CSS"
        css_obj.members = {"member": members}
        wrapper = MagicMock()
        wrapper.css = css_obj
        result = MagicMock()
        result.configure_mock(**{"return": wrapper})
        client._service.getCss = MagicMock(return_value=result)
        client.list_route_partitions = MagicMock(return_value=[
            {"name": "Internal-PT", "description": ""},
        ])
        return client

    def test_emits_one_css_record(self) -> None:
        adapter = _run(self._client_with_one_css([]))
        css_records = list(adapter.get_all("calling_search_space"))
        self.assertEqual(len(css_records), 1)
        self.assertEqual(css_records[0].name, "Internal-CSS")

    def test_membership_records_emit_with_priority(self) -> None:
        adapter = _run(self._client_with_one_css([
            {"routePartitionName": {"_value_1": "Internal-PT"}, "index": 1},
        ]))
        memberships = list(adapter.get_all("css_partition_membership"))
        self.assertEqual(len(memberships), 1)
        self.assertEqual(memberships[0].priority, 1)
        self.assertEqual(memberships[0].partition__name, "Internal-PT")

    def test_member_without_partition_falls_back_to_null(self) -> None:
        adapter = _run(self._client_with_one_css([
            {"routePartitionName": None, "index": 1},
        ]))
        m = next(iter(adapter.get_all("css_partition_membership")))
        self.assertEqual(m.partition__name, adapter.NULL_PARTITION_NAME)

    def test_non_int_index_defaults_to_1(self) -> None:
        adapter = _run(self._client_with_one_css([
            {"routePartitionName": {"_value_1": "Internal-PT"}, "index": "garbage"},
        ]))
        m = next(iter(adapter.get_all("css_partition_membership")))
        self.assertEqual(m.priority, 1)

    def test_getcss_failure_skips_only_memberships(self) -> None:
        """A failed getCss leaves the CSS record but emits no memberships."""
        client = self._client_with_one_css([])
        client._service.getCss = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("calling_search_space"))), 1)
        self.assertEqual(len(list(adapter.get_all("css_partition_membership"))), 0)


# ---------------------------------------------------------------------------
# _load_directory_numbers
# ---------------------------------------------------------------------------


class TestLoadDirectoryNumbers(SimpleTestCase):
    """DNs come from listLine — pattern + partition + alerting name + VM ref."""

    def test_emits_dn_with_partition(self) -> None:
        client = _make_client()
        client.list_route_partitions = MagicMock(return_value=[
            {"name": "Internal-PT", "description": ""},
        ])
        client.list_lines = MagicMock(return_value=[
            {
                "pattern": "1001",
                "routePartitionName": {"_value_1": "Internal-PT"},
                "alertingName": "Alice",
                "voiceMailProfileName": {"_value_1": "default-vmail"},
            },
        ])
        adapter = _run(client)
        dn = next(iter(adapter.get_all("directory_number")))
        self.assertEqual(dn.extension, "1001")
        self.assertEqual(dn.partition__name, "Internal-PT")
        self.assertEqual(dn.alerting_name, "Alice")
        self.assertEqual(dn.voicemail_profile__name, "default-vmail")

    def test_null_voicemail_profile_becomes_none(self) -> None:
        """No voicemail profile assignment → None (not empty string),
        so the FK lookup resolves correctly."""
        client = _make_client()
        client.list_lines = MagicMock(return_value=[{"pattern": "1002"}])
        adapter = _run(client)
        dn = next(iter(adapter.get_all("directory_number")))
        self.assertIsNone(dn.voicemail_profile__name)


# ---------------------------------------------------------------------------
# _load_trunks
# ---------------------------------------------------------------------------


class TestLoadTrunks(SimpleTestCase):
    """Trunks: one SIP trunk per listSipTrunk row, first destination wins."""

    def test_extracts_first_destination(self) -> None:
        client = _make_client()
        client.list_sip_trunks = MagicMock(return_value=[
            {
                "name": "SIP-OUTBOUND",
                "destinations": {"destination": [
                    {"addressIpv4": "203.0.113.10", "port": 5060},
                    {"addressIpv4": "203.0.113.11", "port": 5060},  # 2nd ignored
                ]},
                "transmitUtf8": "true",  # → vendor_extras
            },
        ])
        adapter = _run(client)
        trunk = next(iter(adapter.get_all("trunk")))
        self.assertEqual(trunk.name, "SIP-OUTBOUND")
        self.assertEqual(trunk.destination_address, "203.0.113.10")
        self.assertEqual(trunk.destination_port, 5060)
        self.assertIn("transmitUtf8", trunk.vendor_extras)

    def test_no_destinations_yields_empty_address(self) -> None:
        client = _make_client()
        client.list_sip_trunks = MagicMock(return_value=[
            {"name": "EMPTY-TRK", "destinations": {"destination": []}},
        ])
        adapter = _run(client)
        trunk = next(iter(adapter.get_all("trunk")))
        self.assertEqual(trunk.destination_address, "")
        self.assertIsNone(trunk.destination_port)


# ---------------------------------------------------------------------------
# _load_route_patterns
# ---------------------------------------------------------------------------


class TestLoadRoutePatterns(SimpleTestCase):
    """RoutePattern destinations resolve to RouteList OR Trunk (XOR)."""

    def _client_with_pattern(self, *, destination: dict) -> Any:
        client = _make_client()
        client.list_route_patterns = MagicMock(return_value=[
            {"uuid": "11111111-2222-3333-4444-555555555555"},
        ])
        # getRoutePattern returns a zeep-style object whose .return.routePattern
        # has the fields. We mimic with .return attribute that has .routePattern.
        rp_obj = MagicMock()
        rp_obj.pattern = "9.@"
        rp_obj.routePartitionName = {"_value_1": "PSTN-PT"}
        rp_obj.patternUrgency = "false"
        rp_obj.destination = destination
        rp_obj.callingSearchSpaceName = None
        rp_obj.discardDigits = "PreDot"

        outer = MagicMock()
        outer.return_value = None
        wrapper = MagicMock()
        wrapper.return_value = MagicMock()  # for `getattr(..., "return")`
        wrapper.routePattern = rp_obj

        result = MagicMock()
        result.configure_mock(**{"return": wrapper})
        client._service.getRoutePattern = MagicMock(return_value=result)
        return client

    def test_route_list_target(self) -> None:
        client = self._client_with_pattern(
            destination={"routeListName": {"_value_1": "PRIMARY-RL"}},
        )
        adapter = _run(client)
        rp = next(iter(adapter.get_all("route_pattern")))
        self.assertEqual(rp.target_route_list__name, "PRIMARY-RL")
        self.assertIsNone(rp.target_trunk__name)
        self.assertEqual(rp.discard_digits, "PreDot")

    def test_gateway_trunk_target(self) -> None:
        client = self._client_with_pattern(
            destination={"gatewayName": {"_value_1": "GATEWAY-TRK"}},
        )
        adapter = _run(client)
        rp = next(iter(adapter.get_all("route_pattern")))
        self.assertEqual(rp.target_trunk__name, "GATEWAY-TRK")
        self.assertIsNone(rp.target_route_list__name)

    def test_pattern_missing_uuid_skipped(self) -> None:
        client = _make_client()
        client.list_route_patterns = MagicMock(return_value=[
            {"uuid": ""},  # blank uuid — adapter skips
        ])
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("route_pattern"))), 0)

    def test_pattern_with_no_target_skipped(self) -> None:
        """XOR constraint: rejects pattern with neither RouteList nor Gateway."""
        client = self._client_with_pattern(destination={})
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("route_pattern"))), 0)

    def test_getroutepattern_failure_skips_only_that_pattern(self) -> None:
        client = _make_client()
        client.list_route_patterns = MagicMock(return_value=[
            {"uuid": "11111111-2222-3333-4444-555555555555"},
        ])
        client._service.getRoutePattern = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("route_pattern"))), 0)


# ---------------------------------------------------------------------------
# _load_translation_patterns
# ---------------------------------------------------------------------------


class TestLoadTranslationPatterns(SimpleTestCase):
    """TransPattern is single-pass — listTransPattern gives everything."""

    def test_emits_with_explicit_columns_and_vendor_extras(self) -> None:
        client = _make_client()
        client.list_route_partitions = MagicMock(return_value=[
            {"name": "Translation-PT", "description": ""},
        ])
        client.list_translation_patterns = MagicMock(return_value=[
            {
                "pattern": "9XX",
                "routePartitionName": {"_value_1": "Translation-PT"},
                "callingSearchSpaceName": {"_value_1": "Internal-CSS"},
                "calledPartyTransformationMask": "555XX",
                "callingPartyTransformationMask": "5550000",
                "patternUrgency": "true",
                "blockEnable": "false",
                "discardDigits": "PreDot",
                "digitDiscardInstructionName": {"_value_1": "PreDot"},
                "presentationBit_called": "Default",  # long-tail → vendor_extras
            },
        ])
        adapter = _run(client)
        tp = next(iter(adapter.get_all("translation_pattern")))
        self.assertEqual(tp.pattern, "9XX")
        self.assertEqual(tp.partition__name, "Translation-PT")
        self.assertEqual(tp.css__name, "Internal-CSS")
        self.assertEqual(tp.called_party_transformation_mask, "555XX")
        self.assertTrue(tp.urgent_priority)
        # Long-tail field flows through vendor_extras.
        self.assertIn("presentationBit_called", tp.vendor_extras)

    def test_pattern_without_required_field_skipped(self) -> None:
        client = _make_client()
        client.list_translation_patterns = MagicMock(return_value=[
            {"pattern": ""},  # blank pattern — skipped
        ])
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("translation_pattern"))), 0)


# ---------------------------------------------------------------------------
# _load_route_groups
# ---------------------------------------------------------------------------


class TestLoadRouteGroups(SimpleTestCase):
    """Route groups: scalar metadata + algorithm normalization."""

    def test_emits_route_group_with_algorithm_normalized(self) -> None:
        client = _make_client()
        client.list_route_groups = MagicMock(return_value=[
            {"name": "Group-A", "description": "Primary", "distributionAlgorithm": "Top Down"},
            {"name": "Group-B", "description": "", "distributionAlgorithm": "Circular"},
            {"name": "Group-C", "description": "", "distributionAlgorithm": "TopDown"},
        ])
        adapter = _run(client)
        groups = {g.name: g for g in adapter.get_all("route_group")}
        self.assertEqual(groups["Group-A"].distribution_algorithm, "top_down")
        self.assertEqual(groups["Group-B"].distribution_algorithm, "circular")
        self.assertEqual(groups["Group-C"].distribution_algorithm, "top_down")

    def test_unknown_algorithm_defaults_to_top_down(self) -> None:
        client = _make_client()
        client.list_route_groups = MagicMock(return_value=[
            {"name": "X", "description": "", "distributionAlgorithm": "Mystery"},
        ])
        adapter = _run(client)
        rg = next(iter(adapter.get_all("route_group")))
        self.assertEqual(rg.distribution_algorithm, "top_down")


# ---------------------------------------------------------------------------
# _load_device_profiles (CCM DevicePool → DeviceProfile)
# ---------------------------------------------------------------------------


class TestLoadDeviceProfiles(SimpleTestCase):
    """DevicePool → DeviceProfile with CCM-specific names in vendor_extras."""

    def test_emits_with_extras(self) -> None:
        client = _make_client()
        client._service.listDevicePool = MagicMock(return_value={
            "return": {"devicePool": [{"name": "Default"}, {"name": "SiteA-DP"}]},
        })
        # ``_load_device_profiles`` extracts XFkType wrappers via
        # ``hasattr(val, "_value_1")`` — dicts with ``_value_1`` key don't
        # match. Mock as objects with a real ``_value_1`` attribute.
        def _xfk(value: str) -> Any:
            obj = MagicMock(spec=["_value_1"])
            obj._value_1 = value
            return obj
        dp_detail = {
            "callManagerGroupName": _xfk("Default"),
            "regionName": _xfk("Default"),
            "locationName": _xfk("Hub"),
            "networkLocale": "United States",  # plain string — no XFkType wrapping
        }
        client._service.getDevicePool = MagicMock(return_value={
            "return": {"devicePool": dp_detail},
        })
        adapter = _run(client)
        profiles = {p.name: p for p in adapter.get_all("device_profile")}
        self.assertIn("Default", profiles)
        self.assertIn("SiteA-DP", profiles)
        self.assertEqual(profiles["Default"].vendor_extras["callManagerGroupName"], "Default")
        self.assertEqual(profiles["Default"].vendor_extras["regionName"], "Default")
        self.assertEqual(profiles["Default"].vendor_extras["networkLocale"], "United States")

    def test_blank_name_skipped(self) -> None:
        client = _make_client()
        client._service.listDevicePool = MagicMock(return_value={
            "return": {"devicePool": [{"name": ""}, {"name": "Valid"}]},
        })
        adapter = _run(client)
        names = [p.name for p in adapter.get_all("device_profile")]
        self.assertEqual(names, ["Valid"])

    def test_getdevicepool_failure_still_emits_record(self) -> None:
        """A failed getDevicePool leaves the profile with empty extras
        but doesn't drop the record."""
        client = _make_client()
        client._service.listDevicePool = MagicMock(return_value={
            "return": {"devicePool": [{"name": "Default"}]},
        })
        client._service.getDevicePool = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run(client)
        profiles = list(adapter.get_all("device_profile"))
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].vendor_extras, {})


# ---------------------------------------------------------------------------
# _load_voicemail_profiles
# ---------------------------------------------------------------------------


class TestLoadVoicemailProfiles(SimpleTestCase):
    """VoicemailProfile: pilot DN, mask, default flag, optional vendor_extras."""

    def test_emits_with_pilot_and_mask(self) -> None:
        client = _make_client()
        client._service.listVoiceMailProfile = MagicMock(return_value={
            "return": {"voiceMailProfile": [{"name": "default-vmail"}]},
        })
        client._service.getVoiceMailProfile = MagicMock(return_value={
            "return": {"voiceMailProfile": {
                "voiceMailPilot": {"_value_1": "5550100"},
                "voiceMailboxMask": "555XXXX",
                "isDefault": "true",
                "description": "Default voicemail",
            }},
        })
        adapter = _run(client)
        vp = next(iter(adapter.get_all("voicemail_profile")))
        self.assertEqual(vp.name, "default-vmail")
        self.assertEqual(vp.pilot_dn, "5550100")
        self.assertTrue(vp.is_default)
        self.assertEqual(vp.vendor_extras["voiceMailboxMask"], "555XXXX")

    def test_failed_get_skips_profile(self) -> None:
        """Unlike DevicePool, VoiceMailProfile drops the whole record on
        getVoiceMailProfile failure (pilot DN is critical)."""
        client = _make_client()
        client._service.listVoiceMailProfile = MagicMock(return_value={
            "return": {"voiceMailProfile": [{"name": "broken"}]},
        })
        client._service.getVoiceMailProfile = MagicMock(side_effect=Exception("down"))
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("voicemail_profile"))), 0)


# ---------------------------------------------------------------------------
# _load_call_pickup_groups
# ---------------------------------------------------------------------------


class TestLoadCallPickupGroups(SimpleTestCase):
    """Pickup groups + DN→Group membership via listLine post-pass."""

    def test_emits_pickup_group(self) -> None:
        client = _make_client()
        client._service.listCallPickupGroup = MagicMock(return_value={
            "return": {"callPickupGroup": [{"name": "Floor3-PG"}]},
        })
        client._service.getCallPickupGroup = MagicMock(return_value={
            "return": {"callPickupGroup": {
                "name": "Floor3-PG",
                "pattern": "*333",
                "routePartitionName": {"_value_1": "Internal-PT"},
                "description": "Floor 3 pickup",
            }},
        })
        client.list_route_partitions = MagicMock(return_value=[
            {"name": "Internal-PT", "description": ""},
        ])
        adapter = _run(client)
        pg = next(iter(adapter.get_all("call_pickup_group")))
        self.assertEqual(pg.name, "Floor3-PG")
        self.assertEqual(pg.pattern, "*333")
        self.assertEqual(pg.description, "Floor 3 pickup")

    def test_listcallpickupgroup_failure_no_records(self) -> None:
        """Failed listCallPickupGroup returns no groups (silent skip)."""
        client = _make_client()
        client._service.listCallPickupGroup = MagicMock(
            side_effect=Exception("AXL down"),
        )
        adapter = _run(client)
        self.assertEqual(len(list(adapter.get_all("call_pickup_group"))), 0)
