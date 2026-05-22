"""Tests for the FreePBX source adapter.

Pure unit tests against a mocked ``FreePBXClient`` — no live FreePBX
needed. Asserts that each ``_load_X`` method emits the right DiffSync
records given canned source-side data.

The mock client is deliberately minimal: each test class subclasses
``FreePBXClient.__init__`` to bypass HTTP setup and overrides only the
``list_*`` methods being exercised. That keeps test scope narrow and
makes it obvious which API surface each test covers.

Run via: ``nautobot-server test nautobot_phones.tests.test_freepbx_adapter``
"""

from typing import Any
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from nautobot_phones.integrations.freepbx.adapter import (
    DEFAULT_PARTITION_NAME,
    FreePBXSourceAdapter,
)
from nautobot_phones.integrations.freepbx.client import (
    FreePBXAPIError,
    FreePBXAuthError,
    FreePBXClient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_phone_system_stub(name: str = "LAB-FREEPBX") -> Any:
    """Build a stand-in PhoneSystem object without touching the ORM.

    The adapter only reads ``name``, ``vendor``, ``version``, ``hostname``
    off the record — anything more would require a real DB.
    """
    ps = MagicMock()
    ps.name = name
    ps.vendor = "freepbx"
    ps.version = "17.0.21"
    ps.hostname = "http://freepbx"
    return ps


def _make_client(**overrides: Any) -> FreePBXClient:
    """Construct a FreePBXClient without invoking the real ``httpx.Client``.

    Patches ``httpx.Client`` so the constructor doesn't open a real
    network pool, then applies any per-test attribute overrides.
    """
    with patch("nautobot_phones.integrations.freepbx.client.httpx.Client"):
        client = FreePBXClient(
            base_url="http://freepbx",
            client_id="test-id",
            client_secret="test-secret",
        )
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


def _run_adapter(client: FreePBXClient) -> FreePBXSourceAdapter:
    """Build + load the adapter, returning it for assertion."""
    adapter = FreePBXSourceAdapter(
        client=client,
        phone_system_record=_make_phone_system_stub(),
    )
    adapter.load()
    return adapter


# ---------------------------------------------------------------------------
# Client-level tests
# ---------------------------------------------------------------------------


class TestFreePBXClientPaths(SimpleTestCase):
    """Constants and constructor wiring."""

    def test_endpoint_paths_are_correct(self) -> None:
        """Schema-confirmed: GraphQL is /gql, NOT /graphql."""
        self.assertEqual(FreePBXClient.TOKEN_PATH, "/admin/api/api/token")
        self.assertEqual(FreePBXClient.GRAPHQL_PATH, "/admin/api/api/gql")

    def test_base_url_strips_trailing_slash(self) -> None:
        """Trailing slashes in base_url cause double-slashes in token URLs."""
        client = _make_client()
        client.base_url = "http://freepbx"
        self.assertFalse(client.base_url.endswith("/"))

    def test_db_disabled_when_db_host_unset(self) -> None:
        """DB-direct paths return empty when no DB host configured."""
        client = _make_client(db_host=None)
        self.assertEqual(client.list_trunks(), [])
        self.assertEqual(client.list_outbound_routes(), [])
        self.assertEqual(client.list_ring_groups(), [])

    def test_pickup_groups_is_stub(self) -> None:
        """Stage 6d pickup groups intentionally return empty (data path blocked)."""
        client = _make_client(db_host="freepbx-mariadb")
        self.assertEqual(client.list_pickup_groups(), [])


class TestFreePBXClientErrors(SimpleTestCase):
    """Exception classes carry the right semantics."""

    def test_auth_error_is_distinct_from_api_error(self) -> None:
        """Operators should be able to distinguish token failures from query failures."""
        self.assertTrue(issubclass(FreePBXAuthError, RuntimeError))
        self.assertTrue(issubclass(FreePBXAPIError, RuntimeError))
        self.assertFalse(issubclass(FreePBXAuthError, FreePBXAPIError))


# ---------------------------------------------------------------------------
# Adapter — Stage 4: extensions
# ---------------------------------------------------------------------------


class TestLoadExtensions(SimpleTestCase):
    """``_load_extensions`` emits one DirectoryNumber + Phone per extension."""

    def _mk_client(self) -> FreePBXClient:
        client = _make_client()
        client.list_extensions = MagicMock(return_value=[
            {
                "extensionId": "1001",
                "tech": "pjsip",
                "user": {"extension": "1001", "name": "Alice", "outboundCid": "<5551001>",
                         "voicemail": "novm", "mohclass": "default", "callwaiting": "enabled"},
                "coreDevice": {"dial": "PJSIP/1001", "devicetype": "fixed", "description": "Alice"},
            },
        ])
        # Stub the other resource loaders so we test in isolation.
        client.list_trunks = MagicMock(return_value=[])
        client.list_outbound_routes = MagicMock(return_value=[])
        client.list_voicemail_boxes = MagicMock(return_value={})
        client.list_inbound_routes = MagicMock(return_value=[])
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=[])
        return client

    def test_emits_directory_number_and_phone(self) -> None:
        """Each extension produces exactly one DN + one Phone record."""
        adapter = _run_adapter(self._mk_client())
        dns = list(adapter.get_all("directory_number"))
        phones = list(adapter.get_all("phone"))
        self.assertEqual(len(dns), 1)
        self.assertEqual(len(phones), 1)
        self.assertEqual(dns[0].extension, "1001")
        self.assertEqual(dns[0].alerting_name, "Alice")

    def test_phone_device_name_uses_coreDevice_dial(self) -> None:
        """``device_name`` comes from FreePBX coreDevice.dial (e.g. PJSIP/1001)."""
        adapter = _run_adapter(self._mk_client())
        phone = next(iter(adapter.get_all("phone")))
        self.assertEqual(phone.device_name, "PJSIP/1001")

    def test_phone_kind_is_other_for_freepbx(self) -> None:
        """FreePBX endpoints don't match CCM device-name prefixes — fall back to OTHER."""
        adapter = _run_adapter(self._mk_client())
        phone = next(iter(adapter.get_all("phone")))
        self.assertEqual(phone.device_kind, "other")

    def test_freepbx_tech_preserved_in_vendor_extras(self) -> None:
        """Original FreePBX tech (pjsip/sip/iax2) goes in vendor_extras for fidelity."""
        adapter = _run_adapter(self._mk_client())
        phone = next(iter(adapter.get_all("phone")))
        self.assertEqual(phone.vendor_extras.get("freepbx_tech"), "pjsip")


# ---------------------------------------------------------------------------
# Adapter — Stage 5: trunks + outbound routes
# ---------------------------------------------------------------------------


class TestLoadTrunks(SimpleTestCase):
    """``_load_trunks`` maps FreePBX tech → unified trunk_type."""

    def _mk_client(self, trunks: list[dict]) -> FreePBXClient:
        client = _make_client()
        client.list_extensions = MagicMock(return_value=[])
        client.list_trunks = MagicMock(return_value=trunks)
        client.list_outbound_routes = MagicMock(return_value=[])
        client.list_voicemail_boxes = MagicMock(return_value={})
        client.list_inbound_routes = MagicMock(return_value=[])
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=[])
        return client

    def test_pjsip_maps_to_sip(self) -> None:
        """PJSIP and chan_sip both collapse to vendor-agnostic ``sip``."""
        client = self._mk_client([
            {"trunkid": 1, "tech": "pjsip", "name": "ITSP-1", "outcid": "", "disabled": 0},
            {"trunkid": 2, "tech": "sip",   "name": "ITSP-2", "outcid": "", "disabled": 0},
        ])
        adapter = _run_adapter(client)
        trunks = sorted(adapter.get_all("trunk"), key=lambda t: t.name)
        self.assertEqual(trunks[0].trunk_type, "sip")
        self.assertEqual(trunks[1].trunk_type, "sip")

    def test_dahdi_maps_to_pri(self) -> None:
        """DAHDI is the closest CCM analogue to a T1/E1 PRI card."""
        client = self._mk_client([
            {"trunkid": 1, "tech": "dahdi", "name": "T1-1", "outcid": "", "disabled": 0},
        ])
        adapter = _run_adapter(client)
        trunk = next(iter(adapter.get_all("trunk")))
        self.assertEqual(trunk.trunk_type, "pri")

    def test_freepbx_tech_preserved(self) -> None:
        """vendor_extras preserves the original tech string for traceability."""
        client = self._mk_client([
            {"trunkid": 1, "tech": "pjsip", "name": "ITSP-1", "outcid": "<5550100>",
             "channelid": "fictional-itsp", "disabled": 0},
        ])
        adapter = _run_adapter(client)
        trunk = next(iter(adapter.get_all("trunk")))
        self.assertEqual(trunk.vendor_extras["freepbx_tech"], "pjsip")
        self.assertEqual(trunk.vendor_extras["channelid"], "fictional-itsp")


class TestLoadOutboundRoutes(SimpleTestCase):
    """Outbound route expands to RouteList + RouteGroups + RouteListMembers + RoutePatterns."""

    def _mk_client(self) -> FreePBXClient:
        client = _make_client()
        client.list_extensions = MagicMock(return_value=[])
        client.list_trunks = MagicMock(return_value=[
            {"trunkid": 1, "tech": "pjsip", "name": "ITSP-1", "outcid": "", "disabled": 0},
            {"trunkid": 2, "tech": "pjsip", "name": "ITSP-Backup", "outcid": "", "disabled": 0},
        ])
        client.list_outbound_routes = MagicMock(return_value=[{
            "route_id": 1,
            "name": "NANP",
            "outcid": "<5550100>",
            "patterns": [
                {"prefix": "9",  "match_pattern": "NXXNXXXXXX", "prepend": ""},
                {"prefix": "91", "match_pattern": "NXXNXXXXXX", "prepend": "1"},
            ],
            "trunk_seq": [(1, 1), (2, 2)],
        }])
        client.list_voicemail_boxes = MagicMock(return_value={})
        client.list_inbound_routes = MagicMock(return_value=[])
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=[])
        return client

    def test_synthesizes_route_list_per_outbound_route(self) -> None:
        """One FreePBX outbound route → one RouteList."""
        adapter = _run_adapter(self._mk_client())
        route_lists = list(adapter.get_all("route_list"))
        self.assertEqual(len(route_lists), 1)
        self.assertEqual(route_lists[0].name, "NANP")

    def test_synthesizes_route_group_per_trunk(self) -> None:
        """Each trunk in the priority list gets its own RouteGroup."""
        adapter = _run_adapter(self._mk_client())
        groups = sorted(adapter.get_all("route_group"), key=lambda g: g.name)
        names = [g.name for g in groups]
        self.assertEqual(names, ["ITSP-1", "ITSP-Backup"])

    def test_route_list_members_carry_priority(self) -> None:
        """RouteListMember.priority matches the FreePBX seq."""
        adapter = _run_adapter(self._mk_client())
        members = sorted(adapter.get_all("route_list_member"), key=lambda m: m.priority)
        self.assertEqual([(m.route_group__name, m.priority) for m in members],
                         [("ITSP-1", 1), ("ITSP-Backup", 2)])

    def test_route_group_member_emitted_per_trunk(self) -> None:
        """Each synthesized RouteGroup gets a RouteGroupMember pointing at
        its underlying Trunk (FreePBX = one-trunk-per-group). The GFK
        target_kind is always 'trunk' on the FreePBX side."""
        adapter = _run_adapter(self._mk_client())
        rgms = sorted(adapter.get_all("route_group_member"), key=lambda m: m.target_name)
        self.assertEqual(
            [(m.route_group__name, m.target_kind, m.target_name) for m in rgms],
            [("ITSP-1", "trunk", "ITSP-1"), ("ITSP-Backup", "trunk", "ITSP-Backup")],
        )

    def test_route_patterns_target_the_route_list(self) -> None:
        """Each dial pattern emits a RoutePattern pointing at the parent RouteList."""
        adapter = _run_adapter(self._mk_client())
        patterns = sorted(adapter.get_all("route_pattern"), key=lambda p: p.pattern)
        self.assertEqual(len(patterns), 2)
        self.assertEqual(patterns[0].pattern, "91NXXNXXXXXX")
        self.assertEqual(patterns[0].target_route_list__name, "NANP")
        self.assertIsNone(patterns[0].target_trunk__name)
        self.assertIsNone(patterns[0].target_dn__extension)


# ---------------------------------------------------------------------------
# Adapter — Stage 6b: voicemail profiles
# ---------------------------------------------------------------------------


class TestLoadVoicemailProfiles(SimpleTestCase):
    """``_load_voicemail_profiles`` synthesizes one profile per VM-enabled ext."""

    def _mk_client(self) -> FreePBXClient:
        client = _make_client()
        client.list_extensions = MagicMock(return_value=[
            {"extensionId": "1001", "tech": "pjsip",
             "user": {"extension": "1001", "name": "Alice"},
             "coreDevice": {"dial": "PJSIP/1001"}},
            {"extensionId": "1002", "tech": "pjsip",
             "user": {"extension": "1002", "name": "Bob"},
             "coreDevice": {"dial": "PJSIP/1002"}},
        ])
        client.list_trunks = MagicMock(return_value=[])
        client.list_outbound_routes = MagicMock(return_value=[])
        # Only 1001 has voicemail enabled (non-null context).
        client.list_voicemail_boxes = MagicMock(return_value={
            "1001": {"context": "default", "name": "Alice", "email": "alice@example.com",
                     "attach": "no", "saycid": "no", "envelope": "no", "delete": "no",
                     "pager": ""},
        })
        client.list_inbound_routes = MagicMock(return_value=[])
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=[])
        return client

    def test_one_profile_per_vm_enabled_extension(self) -> None:
        """Extensions without voicemail don't get a synthesized profile."""
        adapter = _run_adapter(self._mk_client())
        profiles = list(adapter.get_all("voicemail_profile"))
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0].name, "vm-1001")

    def test_dn_fk_cross_link(self) -> None:
        """The synthesized profile name lands on the DN's voicemail_profile FK."""
        adapter = _run_adapter(self._mk_client())
        dns = {d.extension: d for d in adapter.get_all("directory_number")}
        self.assertEqual(dns["1001"].voicemail_profile__name, "vm-1001")
        self.assertIsNone(dns["1002"].voicemail_profile__name)


# ---------------------------------------------------------------------------
# Adapter — Stage 6c: inbound routes
# ---------------------------------------------------------------------------


class TestLoadInboundRoutes(SimpleTestCase):
    """``_load_inbound_routes`` maps Extensions: destinations to target_dn."""

    def _mk_client(self, inbound: list[dict]) -> FreePBXClient:
        client = _make_client()
        # Need extension 1001 to exist so target_dn FK can resolve.
        client.list_extensions = MagicMock(return_value=[
            {"extensionId": "1001", "tech": "pjsip",
             "user": {"extension": "1001", "name": "Alice"},
             "coreDevice": {"dial": "PJSIP/1001"}},
        ])
        client.list_trunks = MagicMock(return_value=[])
        client.list_outbound_routes = MagicMock(return_value=[])
        client.list_voicemail_boxes = MagicMock(return_value={})
        client.list_inbound_routes = MagicMock(return_value=inbound)
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=[])
        return client

    def test_did_to_extension_destination(self) -> None:
        """``Extensions: 1001 Alice`` becomes target_dn=(1001, (none))."""
        client = self._mk_client([{
            "extension": "5550100", "cidnum": "", "description": "Main DID",
            "destinationConnection": "Extensions: 1001 Alice",
        }])
        adapter = _run_adapter(client)
        patterns = list(adapter.get_all("route_pattern"))
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].pattern, "5550100")
        self.assertEqual(patterns[0].target_dn__extension, "1001")
        self.assertEqual(patterns[0].target_dn__partition__name, DEFAULT_PARTITION_NAME)

    def test_cid_match_encoded_in_pattern(self) -> None:
        """DID + CID match encodes both in the pattern ``DID/CID``."""
        client = self._mk_client([{
            "extension": "5550100", "cidnum": "1234567890", "description": "CID-filtered DID",
            "destinationConnection": "Extensions: 1001 Alice",
        }])
        adapter = _run_adapter(client)
        pattern = next(iter(adapter.get_all("route_pattern")))
        self.assertEqual(pattern.pattern, "5550100/1234567890")

    def test_non_extension_destination_is_skipped(self) -> None:
        """Queue/IVR/Voicemail destinations have no model — skip cleanly."""
        client = self._mk_client([{
            "extension": "5550100", "cidnum": "", "description": "Goes to queue",
            "destinationConnection": "Queues: 700 Support Queue",
        }])
        adapter = _run_adapter(client)
        self.assertEqual(len(list(adapter.get_all("route_pattern"))), 0)


# ---------------------------------------------------------------------------
# Adapter — Stage 6e: ring groups → hunt subsystem
# ---------------------------------------------------------------------------


class TestLoadRingGroups(SimpleTestCase):
    """Ring groups fan out into HuntPilot + HuntList + LineGroup + members."""

    def _mk_client(self, ring_groups: list[dict]) -> FreePBXClient:
        client = _make_client()
        client.list_extensions = MagicMock(return_value=[])
        client.list_trunks = MagicMock(return_value=[])
        client.list_outbound_routes = MagicMock(return_value=[])
        client.list_voicemail_boxes = MagicMock(return_value={})
        client.list_inbound_routes = MagicMock(return_value=[])
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=ring_groups)
        return client

    def test_one_ring_group_expands_to_five_record_types(self) -> None:
        """1 ring group → 1 HuntPilot + 1 HuntList + 1 LineGroup + 1 HuntListMember + N LineGroupMembers."""
        client = self._mk_client([{
            "grpnum": "600", "strategy": "ringall", "grptime": 20,
            "grplist": "1001-1002", "description": "Eng OnCall",
        }])
        adapter = _run_adapter(client)
        self.assertEqual(len(list(adapter.get_all("hunt_pilot"))), 1)
        self.assertEqual(len(list(adapter.get_all("hunt_list"))), 1)
        self.assertEqual(len(list(adapter.get_all("line_group"))), 1)
        self.assertEqual(len(list(adapter.get_all("hunt_list_member"))), 1)
        self.assertEqual(len(list(adapter.get_all("line_group_member"))), 2)

    def test_strategy_ringall_maps_to_broadcast(self) -> None:
        """FreePBX ``ringall`` strategy → our ``Broadcast`` distribution algorithm."""
        client = self._mk_client([{
            "grpnum": "600", "strategy": "ringall", "grptime": 20,
            "grplist": "1001", "description": "All-Hands",
        }])
        adapter = _run_adapter(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertEqual(lg.distribution_algorithm, "Broadcast")

    def test_strategy_hunt_maps_to_top_down(self) -> None:
        """FreePBX ``hunt`` strategy → ``Top Down``."""
        client = self._mk_client([{
            "grpnum": "601", "strategy": "hunt", "grptime": 20,
            "grplist": "1001", "description": "Sales Hunt",
        }])
        adapter = _run_adapter(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertEqual(lg.distribution_algorithm, "Top Down")

    def test_strategy_memoryhunt_maps_to_circular(self) -> None:
        """FreePBX ``memoryhunt`` strategy → ``Circular``."""
        client = self._mk_client([{
            "grpnum": "602", "strategy": "memoryhunt", "grptime": 20,
            "grplist": "1001", "description": "Support",
        }])
        adapter = _run_adapter(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertEqual(lg.distribution_algorithm, "Circular")

    def test_unknown_strategy_falls_back_to_top_down(self) -> None:
        """Unmapped strategy strings shouldn't crash — default to Top Down."""
        client = self._mk_client([{
            "grpnum": "603", "strategy": "invalid-strategy", "grptime": 20,
            "grplist": "1001", "description": "Test",
        }])
        adapter = _run_adapter(client)
        lg = next(iter(adapter.get_all("line_group")))
        self.assertEqual(lg.distribution_algorithm, "Top Down")

    def test_grplist_order_becomes_line_selection_order(self) -> None:
        """Hyphen-separated grplist order → member line_selection_order."""
        client = self._mk_client([{
            "grpnum": "600", "strategy": "ringall", "grptime": 20,
            "grplist": "1003-1001-1002", "description": "Out-of-order",
        }])
        adapter = _run_adapter(client)
        members = sorted(adapter.get_all("line_group_member"),
                         key=lambda m: m.line_selection_order)
        self.assertEqual([m.directory_number__extension for m in members],
                         ["1003", "1001", "1002"])

    def test_hunt_pilot_pattern_equals_grpnum(self) -> None:
        """The dialed pattern operators use is the ring-group number."""
        client = self._mk_client([{
            "grpnum": "600", "strategy": "ringall", "grptime": 20,
            "grplist": "1001", "description": "Eng",
        }])
        adapter = _run_adapter(client)
        hp = next(iter(adapter.get_all("hunt_pilot")))
        self.assertEqual(hp.pattern, "600")


# ---------------------------------------------------------------------------
# Adapter — Stage 6d: pickup groups (stub behavior)
# ---------------------------------------------------------------------------


class TestLoadPickupGroupsStub(SimpleTestCase):
    """``_load_pickup_groups`` is currently a no-op until the API exposes the data."""

    def test_no_pickup_records_emitted(self) -> None:
        """With the client stub returning [], no CallPickupGroup records appear."""
        client = _make_client()
        client.list_extensions = MagicMock(return_value=[])
        client.list_trunks = MagicMock(return_value=[])
        client.list_outbound_routes = MagicMock(return_value=[])
        client.list_voicemail_boxes = MagicMock(return_value={})
        client.list_inbound_routes = MagicMock(return_value=[])
        client.list_pickup_groups = MagicMock(return_value=[])
        client.list_ring_groups = MagicMock(return_value=[])
        adapter = _run_adapter(client)
        self.assertEqual(len(list(adapter.get_all("call_pickup_group"))), 0)
        self.assertEqual(len(list(adapter.get_all("call_pickup_group_member"))), 0)
