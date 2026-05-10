"""DiffSync source adapter for FreePBX 17.

Mirrors the shape of `cisco_ucm.adapter.CUCMSourceAdapter` so the two
adapters look like siblings — same DiffSync model registrations, same
`top_level` ordering for FK resolution, same `_load_X` private methods
that walk the source-side API and emit DiffSync records.

The vendor-agnostic DiffSync models (registered below) are shared with
the CCM adapter — same `DirectoryNumberModel`, same `PhoneModel`, etc.
That's the whole point: two adapters, one Nautobot schema.

Status: SKELETON. Stage 4 will fill in `_load_extensions` end-to-end.
The class structure is in place so jobs.py can wire it up first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from diffsync import Adapter

from nautobot_phones.diffsync.models import (
    AnalogGatewayModel,
    AnalogPortModel,
    BusyLampFieldModel,
    CallPickupGroupMemberModel,
    CallPickupGroupModel,
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
    DeviceProfileModel,
    DirectoryNumberModel,
    HuntListMemberModel,
    HuntListModel,
    HuntPilotModel,
    LineGroupMemberModel,
    LineGroupModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneServiceUrlModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListMemberModel,
    RouteListModel,
    RoutePatternModel,
    SpeedDialModel,
    TranslationPatternModel,
    TrunkModel,
    VoicemailProfileModel,
)

if TYPE_CHECKING:
    from nautobot_phones.integrations.freepbx.client import FreePBXClient
    from nautobot_phones.models import PhoneSystem


# Synthetic partition name for FreePBX extensions whose context maps to
# the implicit "all internal calling" namespace. Matches the CCM adapter's
# NULL_PARTITION_NAME convention so cross-vendor records sit under a
# consistent "no-partition" partition rather than null.
DEFAULT_PARTITION_NAME = "(none)"


class FreePBXSourceAdapter(Adapter):
    """Source adapter that loads FreePBX records into DiffSync model objects.

    Construction:
        adapter = FreePBXSourceAdapter(
            client=FreePBXClient(...),
            phone_system_record=phone_system_orm_record,
        )
        adapter.load()

    Like the CCM adapter, all vendor-specific data we don't promote to a
    column lands in `vendor_extras` on the relevant DiffSync model. The
    Nautobot adapter doesn't care which vendor produced the diff — it
    just applies whatever the source side emits.
    """

    # DiffSync model registration — must match the Nautobot-side adapter
    # so diffs compute correctly. Same set, same names.
    phone_system = PhoneSystemModel
    partition = PartitionModel
    calling_search_space = CallingSearchSpaceModel
    css_partition_membership = CSSPartitionMembershipModel
    device_profile = DeviceProfileModel
    voicemail_profile = VoicemailProfileModel
    directory_number = DirectoryNumberModel
    phone = PhoneModel
    line = LineModel
    speed_dial = SpeedDialModel
    busy_lamp_field = BusyLampFieldModel
    phone_service_url = PhoneServiceUrlModel
    trunk = TrunkModel
    route_list = RouteListModel
    route_group = RouteGroupModel
    route_list_member = RouteListMemberModel
    route_pattern = RoutePatternModel
    translation_pattern = TranslationPatternModel
    analog_gateway = AnalogGatewayModel
    analog_port = AnalogPortModel
    hunt_list = HuntListModel
    line_group = LineGroupModel
    hunt_list_member = HuntListMemberModel
    line_group_member = LineGroupMemberModel
    hunt_pilot = HuntPilotModel
    call_pickup_group = CallPickupGroupModel
    call_pickup_group_member = CallPickupGroupMemberModel

    # Same load order as the CCM adapter — FK targets before referrers,
    # through-tables after their parents.
    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "css_partition_membership",
        "device_profile",
        "voicemail_profile",
        "directory_number",
        "phone",
        "line",
        "speed_dial",
        "busy_lamp_field",
        "phone_service_url",
        "trunk",
        "route_list",
        "route_group",
        "route_list_member",
        "route_pattern",
        "translation_pattern",
        "analog_gateway",
        "analog_port",
        "line_group",
        "hunt_list",
        "line_group_member",
        "hunt_list_member",
        "hunt_pilot",
        "call_pickup_group",
        "call_pickup_group_member",
    )

    type = "freepbx"

    def __init__(
        self,
        *args,
        client: "FreePBXClient",
        phone_system_record: "PhoneSystem",
        job=None,
        **kwargs,
    ) -> None:
        """Take a configured FreePBXClient and the PhoneSystem record it belongs to.

        `phone_system_record` is the Nautobot PhoneSystem ORM instance —
        we need its name + vendor for the synthetic phone_system DiffSync
        record we emit (the FreePBX cluster IS the phone system).
        """
        super().__init__(*args, **kwargs)
        self.client = client
        self.phone_system_record = phone_system_record
        self.job = job

    # -------------------------------------------------------------- load

    def load(self) -> None:
        """Walk FreePBX's GraphQL API and populate DiffSync models.

        Stage 4 implementation: extensions only. Stages 5+ extend this
        to cover trunks, routes, ring groups, etc. For now we emit the
        PhoneSystem record + a synthetic "(none)" Partition so the
        DiffSync model graph is internally consistent.
        """
        ps = self.phone_system_record
        self.add(self.phone_system(
            name=ps.name,
            vendor=ps.vendor,
            version=ps.version,
            hostname=ps.hostname,
        ))
        # Synthetic default partition — matches the "(none)" convention
        # the CCM adapter uses. Even though FreePBX has "contexts" rather
        # than partitions, every extension belongs to *something*, and
        # mapping the implicit default-context to "(none)" gives us a
        # Partition record to FK against.
        self.add(self.partition(
            name=DEFAULT_PARTITION_NAME,
            phone_system__name=ps.name,
            description="",
        ))

        # Stage 4: extensions → DirectoryNumber + Phone
        # Captures the extension list so stage-6b can cross-reference
        # without re-querying GraphQL.
        self._extension_ids: list[str] = []
        self._load_extensions(ps.name)

        # Stage 5: trunks + outbound routes (read direct from MariaDB —
        # the api module's GraphQL schema doesn't expose these yet).
        self._load_trunks(ps.name)
        self._load_outbound_routes(ps.name)

        # Stage 6b: voicemail boxes per extension. Updates already-emitted
        # DirectoryNumber records to point at the synthesized profile FK.
        self._load_voicemail_profiles(ps.name)

        # Stage 6c: inbound routes → RoutePattern (incoming-side).
        self._load_inbound_routes(ps.name)

        # Stages 6d+:
        # self._load_ring_groups(ps.name)
        # self._load_pickup_groups(ps.name)

    # -------------------------------------------- per-resource loaders

    def _load_extensions(self, ps_name: str) -> None:
        """Walk fetchAllExtensions, emit one DirectoryNumber + Phone per record.

        Mapping (FreePBX → unified):
          - extensionId  → DirectoryNumber.extension
          - user.name    → DirectoryNumber.alerting_name
          - coreDevice.dial (e.g. "PJSIP/1001") → Phone.device_name
          - tech (pjsip/sip/iax2/dahdi) → Phone.device_kind="other"
            (we don't have FreePBX-specific values in PhoneDeviceKindChoices;
            tech goes into vendor_extras for fidelity)
          - user.outboundCid, voicemail status, ring/transfer destinations,
            recording prefs → vendor_extras

        FreePBX has no concept of partitions, so all DNs land under our
        synthetic "(none)" partition. Operators querying "show me phones
        in partition X" won't get FreePBX results, which is expected —
        that's a CCM-flavored query that doesn't translate.
        """
        for ext in self.client.list_extensions():
            extension_id = (ext.get("extensionId") or "").strip()
            if not extension_id:
                continue
            self._extension_ids.append(extension_id)
            user = ext.get("user") or {}
            core_device = ext.get("coreDevice") or {}
            tech = (ext.get("tech") or "").strip()
            dial = (core_device.get("dial") or "").strip()
            name = (user.get("name") or "").strip()

            # Emit DirectoryNumber.
            dn_extras: dict = {}
            for fld in ("voicemail", "outboundCid", "ringtimer",
                        "noanswerDestination", "busyDestination",
                        "chanunavailDestination", "mohclass", "callwaiting",
                        "recording_priority"):
                v = user.get(fld)
                if v not in (None, "", 0):
                    dn_extras[fld] = v
            self.add(self.directory_number(
                extension=extension_id,
                partition__name=DEFAULT_PARTITION_NAME,
                partition__phone_system__name=ps_name,
                alerting_name=name,
                voicemail_profile__name=None,  # stage-5 — synthesized profiles
                vendor_extras=dn_extras,
            ))

            # Emit Phone. device_name uses the dial string (e.g. "PJSIP/1001")
            # so it's deterministic across runs and matches how Asterisk
            # internally identifies the endpoint.
            device_name = dial or f"{tech.upper()}/{extension_id}" or extension_id
            phone_extras: dict = {"freepbx_tech": tech}
            for fld in ("devicetype", "description", "emergencyCid"):
                v = core_device.get(fld)
                if v not in (None, ""):
                    phone_extras[fld] = v
            self.add(self.phone(
                device_name=device_name,
                phone_system__name=ps_name,
                mac_address=None,  # FreePBX doesn't track MAC at the SIP-peer level
                device_kind="other",
                description=name,
                registration_status="unknown",
                last_registered_ip=None,
                active_load="",
                inactive_load="",
                live_login_user="",
                status_reason="",
                live_status_polled_at=None,
                media_zone="",
                device_profile__name=None,
                owner_user_id="",
                user_locale="",
                dnd_status=False,
                vendor_extras=phone_extras,
            ))

    # ----- Trunks + Outbound Routes (DB-direct path) -------------------------
    # FreePBX 17's `api` module 17.0.6 doesn't expose trunks or outbound
    # routes in GraphQL, so we go to MariaDB read-only. The schemas
    # (`trunks`, `outbound_routes`, `outbound_route_patterns`,
    # `outbound_route_trunks`) have been stable since FreePBX 13.

    # FreePBX `tech` value → our TrunkTypeChoices value. PJSIP/SIP both
    # collapse to "sip" since our schema doesn't distinguish; the original
    # tech string is preserved in vendor_extras["freepbx_tech"].
    _TECH_TO_TRUNK_TYPE = {
        "pjsip": "sip",
        "sip": "sip",
        "iax2": "sip",  # closest match — IAX2 is Asterisk-only, no CCM analogue
        "dahdi": "pri",  # T1/E1 PRI cards on DAHDI
        "custom": "sip",
    }

    def _load_trunks(self, ps_name: str) -> None:
        """Walk FreePBX trunks, emit one Trunk DiffSync record each.

        FreePBX's tech (pjsip/sip/iax2/dahdi/custom) maps to our
        vendor-agnostic TrunkTypeChoices via _TECH_TO_TRUNK_TYPE. The
        original tech string + the channel ID (provider) and outcid
        live in vendor_extras for fidelity.
        """
        for t in self.client.list_trunks():
            name = (t.get("name") or "").strip()
            if not name:
                continue
            tech = (t.get("tech") or "").strip().lower()
            trunk_type = self._TECH_TO_TRUNK_TYPE.get(tech, "sip")
            extras: dict = {"freepbx_tech": tech}
            for fld in ("channelid", "outcid", "provider", "maxchans", "dialoutprefix"):
                v = t.get(fld)
                if v not in (None, ""):
                    extras[fld] = v
            if t.get("disabled"):
                extras["disabled"] = True
            self.add(self.trunk(
                name=name,
                phone_system__name=ps_name,
                trunk_type=trunk_type,
                # FreePBX trunk endpoint URL lives in tech-specific config
                # tables (sip_settings, pjsip.* etc.) — defer to a deeper
                # pull pass; for now we just record the trunk's existence.
                destination_address="",
                destination_port=None,
                vendor_extras=extras,
            ))

    def _load_outbound_routes(self, ps_name: str) -> None:
        """Walk FreePBX outbound routes, emit RouteList + RouteListMember +
        RoutePattern records.

        Mapping rationale: a FreePBX outbound route holds (1) a list of
        dial patterns and (2) a priority-ordered trunk list. Our model
        graph splits this in two:
          - The trunk-priority list maps to RouteList + RouteListMember
            (one RouteList per FreePBX route, one RouteGroup synthesized
            per trunk so RouteListMember.route_group has something real
            to FK against).
          - The dial patterns map to one RoutePattern per pattern row,
            all targeting the synthesized RouteList.

        This matches how CCM operators think about the same concept —
        you build a RouteList with prioritized trunk groups, then point
        N RoutePatterns at it.
        """
        # We need to look up trunk names by id. Build a small map first.
        trunks_by_id: dict[int, str] = {}
        for t in self.client.list_trunks():
            trunks_by_id[int(t["trunkid"])] = (t.get("name") or "").strip()

        for r in self.client.list_outbound_routes():
            route_id = int(r["route_id"])
            route_name = (r.get("name") or f"route-{route_id}").strip()

            # 1) RouteList for this FreePBX route.
            route_extras: dict = {}
            if r.get("outcid"):
                route_extras["outcid"] = r["outcid"]
            if r.get("emergency_route"):
                route_extras["emergency_route"] = r["emergency_route"]
            if r.get("intracompany_route"):
                route_extras["intracompany_route"] = r["intracompany_route"]
            self.add(self.route_list(
                name=route_name,
                phone_system__name=ps_name,
                description="",
                vendor_extras=route_extras,
            ))

            # 2) Each trunk gets a synthesized RouteGroup (named after the
            # trunk) so the RouteListMember through-table has a real FK target.
            # FreePBX doesn't have CCM's trunk-vs-group distinction; one
            # group-per-trunk is the cleanest unification.
            seen_groups: set[str] = set()
            for seq, trunk_id in r.get("trunk_seq", []):
                trunk_name = trunks_by_id.get(int(trunk_id))
                if not trunk_name:
                    continue
                if trunk_name not in seen_groups:
                    self.add(self.route_group(
                        name=trunk_name,
                        phone_system__name=ps_name,
                        description=f"Synthesized for FreePBX trunk {trunk_name!r}",
                        distribution_algorithm="top_down",
                        vendor_extras={"synthesized_from": "freepbx_trunk"},
                    ))
                    seen_groups.add(trunk_name)
                # Emit the through-table row so the RouteList's RouteGroup
                # priority is operator-visible. seq from FreePBX is 1-based;
                # we keep that semantic since RouteListMember.priority docs
                # say "lower number = evaluated first".
                self.add(self.route_list_member(
                    route_list__name=route_name,
                    route_list__phone_system__name=ps_name,
                    route_group__name=trunk_name,
                    priority=int(seq),
                ))

            # 3) One RoutePattern per pattern row, targeting this RouteList.
            for idx, p in enumerate(r.get("patterns", []) or []):
                # Build the dialed pattern: prefix + match string. Asterisk-style
                # patterns use N/X/Z/[]; we preserve them literally so the
                # operator-facing pattern is the same as in FreePBX.
                pattern_str = (p.get("prefix") or "") + (p.get("match_pattern") or "")
                if not pattern_str:
                    continue
                pat_extras: dict = {}
                if p.get("prepend"):
                    pat_extras["prepend_digits"] = p["prepend"]
                self.add(self.route_pattern(
                    pattern=pattern_str,
                    partition__name=DEFAULT_PARTITION_NAME,
                    partition__phone_system__name=ps_name,
                    css__name=None,
                    target_trunk__name=None,
                    target_route_list__name=route_name,
                    urgent=False,
                    discard_digits="",
                ))

    # ----- Voicemail profiles ------------------------------------------------

    def _load_voicemail_profiles(self, ps_name: str) -> None:
        """For each VM-enabled extension, emit a VoicemailProfile + cross-link the DN.

        FreePBX's voicemail config is per-extension (no shared profiles
        like CCM has), so we synthesize one ``VoicemailProfile`` per
        extension that has VM enabled. Profile name follows
        ``vm-<extensionId>`` so it's stable across syncs and
        deterministic for diff comparison.

        Cross-linking the DN means re-emitting it with the FK populated.
        DiffSync's update path detects the changed attribute and applies
        it — no need to delete-and-recreate.
        """
        if not self._extension_ids:
            return
        boxes = self.client.list_voicemail_boxes(self._extension_ids)
        if not boxes:
            return

        for ext_id, vm in boxes.items():
            profile_name = f"vm-{ext_id}"
            extras: dict = {}
            for fld in ("context", "pager", "attach", "saycid", "envelope", "delete"):
                v = vm.get(fld)
                if v not in (None, ""):
                    extras[fld] = v
            self.add(self.voicemail_profile(
                name=profile_name,
                phone_system__name=ps_name,
                description=(vm.get("name") or ext_id),
                pilot_dn="",      # FreePBX uses the global *97 feature code
                is_default=False,
                vendor_extras=extras,
            ))

            # Re-emit the DN with the voicemail_profile__name FK set.
            # Skip if we don't have the matching DN in our diff (defensive
            # — should always exist after _load_extensions but extension
            # lookup is by extensionId not by DN-extension if those differ).
            dn = self.get(self.directory_number, {
                "extension": ext_id,
                "partition__name": DEFAULT_PARTITION_NAME,
                "partition__phone_system__name": ps_name,
            }) if hasattr(self, "get") else None
            if dn is not None:
                dn.voicemail_profile__name = profile_name

    # ----- Inbound routes ---------------------------------------------------

    # destinationConnection from FreePBX is rendered as
    # "<TypePrefix>: <id> <description>" — parse out the type and id
    # so we can pick the correct RoutePattern target FK.
    _DEST_PARSERS = {
        "Extensions": "ext",
        "Ring Groups": "ringgroup",   # mapped to target_route_list once stage 6e lands
        # IVR / Queues / Voicemail / Terminate / Custom — currently skipped
        # since there's no RoutePattern target FK to point them at.
    }

    def _load_inbound_routes(self, ps_name: str) -> None:
        """Walk allInboundRoutes, emit one RoutePattern (incoming side) per record.

        FreePBX inbound routes match on a DID (and optionally CID) and
        send the call to a destination — typically an extension, ring
        group, queue, IVR, or voicemail. Our schema has RoutePattern
        with three mutually-exclusive target FKs (target_trunk,
        target_route_list, target_dn); we map by destination type.

        Currently we only handle ``Extensions:`` destinations (target_dn).
        Ring-group destinations get a TODO once stage-6e lands; queue/
        IVR destinations are skipped (no model). Skipped routes log
        their destination string so operators can audit coverage.
        """
        import re
        ext_re = re.compile(r"^Extensions:\s+(\d+)")

        for r in self.client.list_inbound_routes():
            did = (r.get("extension") or "").strip()
            if not did:
                continue
            cidnum = (r.get("cidnum") or "").strip()
            # If both DID + CID are set, FreePBX matches on the pair; encode
            # that into the pattern as "<DID>/<CID>" for visibility.
            pattern = f"{did}/{cidnum}" if cidnum else did

            dest_str = (r.get("destinationConnection") or "").strip()
            target_dn_extension = None
            m = ext_re.match(dest_str)
            if m:
                target_dn_extension = m.group(1)

            if target_dn_extension is None:
                # Non-extension destination (ring group / queue / IVR /
                # voicemail / terminate / custom). Skip for now —
                # logging would need a job reference; defer.
                continue

            self.add(self.route_pattern(
                pattern=pattern,
                partition__name=DEFAULT_PARTITION_NAME,
                partition__phone_system__name=ps_name,
                css__name=None,
                # XOR target — for inbound routes hitting an extension,
                # only target_dn is set.
                target_trunk__name=None,
                target_route_list__name=None,
                target_dn__extension=target_dn_extension,
                target_dn__partition__name=DEFAULT_PARTITION_NAME,
                urgent=False,
                discard_digits="",
            ))
