"""Tests for the CCM AXL source adapter.

Pure unit tests against a mocked ``AXLClient`` — no live cluster
needed. Mirrors the FreePBX adapter test pattern (stage 6.5): each
test stubs only the client methods the loader under test touches,
plus the underlying ``_service.getX`` for per-record enrichment paths.

Run via: ``nautobot-server test nautobot_phones.tests.test_cisco_ucm_adapter``
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


def _make_minimal_client() -> Any:
    """Mock AXLClient where every list_*/get_* returns empty/zero by default.

    Per-test methods override only the surfaces they care about. Keeps each
    test's scope obvious — what's mocked is what's being asserted on.
    """
    client = MagicMock()
    client.list_route_lists = MagicMock(return_value=[])
    client.list_route_groups = MagicMock(return_value=[])
    client.list_partitions = MagicMock(return_value=[])
    client.list_css = MagicMock(return_value=[])
    client.list_directory_numbers = MagicMock(return_value=[])
    client.list_phones = MagicMock(return_value=[])
    client.list_sip_trunks = MagicMock(return_value=[])
    client.list_route_patterns = MagicMock(return_value=[])
    client.list_translation_patterns = MagicMock(return_value=[])
    client.list_device_pools = MagicMock(return_value=[])
    client.list_voicemail_profiles = MagicMock(return_value=[])
    client.list_call_pickup_groups = MagicMock(return_value=[])
    client.list_gateways = MagicMock(return_value=[])
    client._list = MagicMock(return_value=[])
    # _service.* for per-record enrichment calls — all return empty
    # zeep-style wrappers (``{"return": {<modelname>: {...}}}``).
    client._service = MagicMock()
    client._service.getRouteList = MagicMock(return_value={"return": {"routeList": None}})
    client._service.getRouteGroup = MagicMock(return_value={"return": {"routeGroup": None}})
    client._service.getHuntList = MagicMock(return_value={"return": {"huntList": None}})
    client._service.getLineGroup = MagicMock(return_value={"return": {"lineGroup": None}})
    client._service.getGateway = MagicMock(return_value={"return": {"gateway": None}})
    client._service.getDevicePool = MagicMock(return_value={"return": {"devicePool": None}})
    client._service.getVoiceMailProfile = MagicMock(return_value={"return": {"voiceMailProfile": None}})
    client._service.getCallPickupGroup = MagicMock(return_value={"return": {"callPickupGroup": None}})
    client._service.getRoutePattern = MagicMock(return_value={"return": {"routePattern": None}})
    return client


def _run_adapter(client: Any) -> CUCMSourceAdapter:
    """Build + load the adapter, returning it for assertion."""
    adapter = CUCMSourceAdapter(
        client=client,
        phone_system_record=_make_phone_system_stub(),
        enrich_phone_lines=False,
        enrich_phone_ip=False,
    )
    adapter.load()
    return adapter


# ---------------------------------------------------------------------------
# RouteList → RouteListMember through-table emission
# ---------------------------------------------------------------------------


class TestLoadRouteListsThroughTable(SimpleTestCase):
    """``_load_route_lists`` emits RouteList records AND RouteListMember rows."""

    def _client_with_route_list(self, members: list[dict]) -> Any:
        """Build a client where listRouteList returns 1 list and getRouteList
        returns the provided members."""
        client = _make_minimal_client()
        # listRouteList — scalar-only metadata
        client.list_route_lists = MagicMock(return_value=[
            {"name": "PrimaryRL", "description": "Primary outbound route list"},
        ])
        # getRouteList — full record with nested members
        client._service.getRouteList = MagicMock(return_value={
            "return": {"routeList": {
                "name": "PrimaryRL",
                "members": {"member": members},
            }}
        })
        return client

    def test_emits_one_route_list_record(self) -> None:
        """The RouteList itself shows up regardless of members."""
        client = self._client_with_route_list([])
        adapter = _run_adapter(client)
        rls = list(adapter.get_all("route_list"))
        self.assertEqual(len(rls), 1)
        self.assertEqual(rls[0].name, "PrimaryRL")
        self.assertEqual(rls[0].description, "Primary outbound route list")

    def test_through_table_rows_carry_priority(self) -> None:
        """Each member emits a RouteListMember with priority from selectionOrder."""
        client = self._client_with_route_list([
            {"routeGroupName": {"_value_1": "Group-PRI"}, "selectionOrder": 1},
            {"routeGroupName": {"_value_1": "Group-SIP"}, "selectionOrder": 2},
        ])
        adapter = _run_adapter(client)
        members = sorted(adapter.get_all("route_list_member"), key=lambda m: m.priority)
        self.assertEqual(
            [(m.route_group__name, m.priority) for m in members],
            [("Group-PRI", 1), ("Group-SIP", 2)],
        )

    def test_membership_links_to_parent_route_list(self) -> None:
        """The through-table FK chain resolves to the parent RouteList."""
        client = self._client_with_route_list([
            {"routeGroupName": {"_value_1": "Group-PRI"}, "selectionOrder": 1},
        ])
        adapter = _run_adapter(client)
        m = next(iter(adapter.get_all("route_list_member")))
        self.assertEqual(m.route_list__name, "PrimaryRL")
        self.assertEqual(m.route_list__phone_system__name, "LAB-CCM")

    def test_single_member_not_list_is_normalized(self) -> None:
        """AXL/zeep sometimes returns a scalar instead of a list for 1-element
        member collections. Loader should normalize."""
        client = self._client_with_route_list([])
        # Override directly with a non-list .member to simulate zeep behavior.
        client._service.getRouteList = MagicMock(return_value={
            "return": {"routeList": {
                "name": "PrimaryRL",
                "members": {"member": {
                    "routeGroupName": {"_value_1": "Group-Only"},
                    "selectionOrder": 1,
                }},
            }}
        })
        adapter = _run_adapter(client)
        members = list(adapter.get_all("route_list_member"))
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].route_group__name, "Group-Only")

    def test_get_route_list_failure_logs_no_membership(self) -> None:
        """A failed getRouteList call leaves the RouteList without members
        — adapter doesn't crash; just skips."""
        client = _make_minimal_client()
        client.list_route_lists = MagicMock(return_value=[
            {"name": "RL-A", "description": ""},
        ])
        client._service.getRouteList = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run_adapter(client)
        # Parent record still emitted.
        self.assertEqual(len(list(adapter.get_all("route_list"))), 1)
        # No membership rows from a failed enrichment.
        self.assertEqual(len(list(adapter.get_all("route_list_member"))), 0)

    def test_missing_route_group_name_is_skipped(self) -> None:
        """Members with null routeGroupName don't emit broken FK rows."""
        client = self._client_with_route_list([
            {"routeGroupName": None, "selectionOrder": 1},
            {"routeGroupName": {"_value_1": "Valid"}, "selectionOrder": 2},
        ])
        adapter = _run_adapter(client)
        members = list(adapter.get_all("route_list_member"))
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].route_group__name, "Valid")

    def test_non_int_selection_order_falls_back_to_1(self) -> None:
        """selectionOrder is sometimes returned as a string (zeep quirk).
        Coerce; on parse failure default to 1."""
        client = self._client_with_route_list([
            {"routeGroupName": {"_value_1": "Group-A"}, "selectionOrder": "2"},
            {"routeGroupName": {"_value_1": "Group-B"}, "selectionOrder": "garbage"},
        ])
        adapter = _run_adapter(client)
        priorities = sorted(m.priority for m in adapter.get_all("route_list_member"))
        self.assertEqual(priorities, [1, 2])

    def test_empty_route_list_name_is_skipped(self) -> None:
        """listRouteList rows missing a name are dropped — defensive
        against bad AXL responses."""
        client = _make_minimal_client()
        client.list_route_lists = MagicMock(return_value=[
            {"name": "", "description": "nameless"},
            {"name": "Valid", "description": ""},
        ])
        client._service.getRouteList = MagicMock(return_value={
            "return": {"routeList": {"name": "Valid", "members": {"member": []}}}
        })
        adapter = _run_adapter(client)
        rls = list(adapter.get_all("route_list"))
        self.assertEqual(len(rls), 1)
        self.assertEqual(rls[0].name, "Valid")


# ---------------------------------------------------------------------------
# RouteGroupMember GFK through-table emission
# ---------------------------------------------------------------------------


class TestLoadRouteGroupMembers(SimpleTestCase):
    """``_load_route_group_members`` emits RouteGroupMember rows via getRouteGroup.

    The GFK target_kind is disambiguated by looking up the device name
    against the already-loaded Trunk + AnalogGateway DiffSync stores, so
    tests need to seed those via the mocked client.
    """

    def _client_with_route_group(
        self,
        members: list[dict],
        *,
        trunks: list[str] | None = None,
        gateways: list[str] | None = None,
    ) -> Any:
        """Seed listRouteGroup with one group, getRouteGroup with members,
        and (optionally) trunks / analog gateways for kind disambiguation."""
        client = _make_minimal_client()
        client.list_route_groups = MagicMock(return_value=[
            {"name": "Group-A", "description": "", "distributionAlgorithm": "Top Down"},
        ])
        client._service.getRouteGroup = MagicMock(return_value={
            "return": {"routeGroup": {
                "name": "Group-A",
                "members": {"member": members},
            }}
        })
        if trunks:
            client.list_sip_trunks = MagicMock(return_value=[
                {"name": t, "destinations": {"destination": []}} for t in trunks
            ])
        if gateways:
            # listGateway uses `domainName` not `name` — caught a real
            # adapter quirk when this test was first authored.
            client.list_gateways = MagicMock(return_value=[
                {"domainName": g, "product": "VG224", "protocol": "MGCP"} for g in gateways
            ])
        return client

    def test_trunk_target_emits_rgm_with_trunk_kind(self) -> None:
        """A device matching an already-loaded Trunk gets kind='trunk'."""
        client = self._client_with_route_group(
            members=[
                {"deviceName": {"_value_1": "SIP-TRK-1"}, "deviceSelectionOrder": 1},
            ],
            trunks=["SIP-TRK-1"],
        )
        adapter = _run_adapter(client)
        rgms = list(adapter.get_all("route_group_member"))
        self.assertEqual(len(rgms), 1)
        self.assertEqual(rgms[0].target_kind, "trunk")
        self.assertEqual(rgms[0].target_name, "SIP-TRK-1")
        self.assertEqual(rgms[0].priority, 1)
        self.assertEqual(rgms[0].route_group__name, "Group-A")

    def test_analog_gateway_target_emits_rgm_with_analoggateway_kind(self) -> None:
        """A device matching an AnalogGateway gets kind='analoggateway'."""
        client = self._client_with_route_group(
            members=[
                {"deviceName": {"_value_1": "VG224-LAB"}, "deviceSelectionOrder": 2},
            ],
            gateways=["VG224-LAB"],
        )
        adapter = _run_adapter(client)
        rgms = list(adapter.get_all("route_group_member"))
        self.assertEqual(len(rgms), 1)
        self.assertEqual(rgms[0].target_kind, "analoggateway")
        self.assertEqual(rgms[0].target_name, "VG224-LAB")

    def test_mixed_membership_emits_both_kinds(self) -> None:
        """A single RouteGroup can contain a Trunk + an AnalogGateway."""
        client = self._client_with_route_group(
            members=[
                {"deviceName": {"_value_1": "SIP-PRIMARY"}, "deviceSelectionOrder": 1},
                {"deviceName": {"_value_1": "VG-FAILOVER"}, "deviceSelectionOrder": 2},
            ],
            trunks=["SIP-PRIMARY"],
            gateways=["VG-FAILOVER"],
        )
        adapter = _run_adapter(client)
        rgms = sorted(adapter.get_all("route_group_member"), key=lambda r: r.priority)
        self.assertEqual(
            [(r.target_kind, r.target_name, r.priority) for r in rgms],
            [("trunk", "SIP-PRIMARY", 1), ("analoggateway", "VG-FAILOVER", 2)],
        )

    def test_unknown_device_kind_is_silently_skipped(self) -> None:
        """A device name that matches neither a Trunk nor an AnalogGateway
        is dropped — likely a Phone or CTI Route Point we don't model
        as a route-group target."""
        client = self._client_with_route_group(
            members=[
                {"deviceName": {"_value_1": "UNKNOWN-DEV"}, "deviceSelectionOrder": 1},
                {"deviceName": {"_value_1": "REAL-TRUNK"}, "deviceSelectionOrder": 2},
            ],
            trunks=["REAL-TRUNK"],
        )
        adapter = _run_adapter(client)
        rgms = list(adapter.get_all("route_group_member"))
        self.assertEqual(len(rgms), 1)
        self.assertEqual(rgms[0].target_name, "REAL-TRUNK")

    def test_get_route_group_failure_drops_only_membership(self) -> None:
        """A failed getRouteGroup leaves the RouteGroup itself in place —
        but emits no RouteGroupMember rows for that group."""
        client = self._client_with_route_group(members=[], trunks=["T"])
        client._service.getRouteGroup = MagicMock(side_effect=Exception("AXL down"))
        adapter = _run_adapter(client)
        self.assertEqual(len(list(adapter.get_all("route_group"))), 1)
        self.assertEqual(len(list(adapter.get_all("route_group_member"))), 0)

    def test_single_member_not_in_list_is_normalized(self) -> None:
        """zeep quirk: 1-element collections come back as scalars instead
        of lists — loader normalizes."""
        client = self._client_with_route_group(members=[], trunks=["LONELY-TRK"])
        client._service.getRouteGroup = MagicMock(return_value={
            "return": {"routeGroup": {
                "name": "Group-A",
                "members": {"member": {
                    "deviceName": {"_value_1": "LONELY-TRK"},
                    "deviceSelectionOrder": 1,
                }},
            }}
        })
        adapter = _run_adapter(client)
        rgms = list(adapter.get_all("route_group_member"))
        self.assertEqual(len(rgms), 1)
        self.assertEqual(rgms[0].target_name, "LONELY-TRK")

    def test_non_int_selection_order_falls_back_to_1(self) -> None:
        """deviceSelectionOrder as a non-int string defaults to priority 1."""
        client = self._client_with_route_group(
            members=[
                {"deviceName": {"_value_1": "T1"}, "deviceSelectionOrder": "garbage"},
            ],
            trunks=["T1"],
        )
        adapter = _run_adapter(client)
        rgms = list(adapter.get_all("route_group_member"))
        self.assertEqual(rgms[0].priority, 1)

    def test_missing_device_name_skipped(self) -> None:
        """Member with a null deviceName ref doesn't crash the loader."""
        client = self._client_with_route_group(
            members=[
                {"deviceName": None, "deviceSelectionOrder": 1},
                {"deviceName": {"_value_1": "VALID-T"}, "deviceSelectionOrder": 2},
            ],
            trunks=["VALID-T"],
        )
        adapter = _run_adapter(client)
        rgms = list(adapter.get_all("route_group_member"))
        self.assertEqual(len(rgms), 1)
        self.assertEqual(rgms[0].target_name, "VALID-T")
