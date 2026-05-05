"""DiffSync source adapter that loads from a Cisco UCM cluster via AXL.

This adapter is read-only — it only loads from CUCM, never writes back.
DiffSync's create/update/delete actions land on the *Nautobot-side*
adapter (PhonesNautobotAdapter); from CUCM's perspective, this side is
the source of truth that Nautobot mirrors.

`load()` walks the AXL listX operations and instantiates DiffSync model
instances for each row. Defensive `getattr(obj, "field", None)` access
on every AXL object so version-specific field additions/removals don't
break the adapter — important since we target AXL 15.x but customers
may run 12.5 or 14.

The adapter takes an AXLClient instance (typically built from a
PhoneSystem record's secrets_group). For testing, pass any object that
duck-types the AXLClient interface (the Job constructs the real client;
unit tests pass mocks).
"""

from __future__ import annotations

from typing import Any

from diffsync import Adapter

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


def _axl_bool(v: Any) -> bool:
    """Coerce AXL's stringly-typed booleans into real bools.

    AXL returns booleans as the literal strings ``"true"`` / ``"false"``
    (lowercase), occasionally with surrounding whitespace, and very
    occasionally as actual Python bools when zeep parses an xsd:boolean
    cleanly. Treat anything that isn't an affirmative string as False.
    """
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def _get(obj: Any, name: str, default=None) -> Any:
    """Tolerant attribute access for AXL response objects.

    Zeep response objects expose attributes via `getattr` only — they
    don't have a working `.get()` method despite implementing partial
    Mapping semantics. Plain dicts (for nested zeep types like
    routePartitionName.{_value_1}) need `.get()`. Handle both.

    AttributeError on zeep is non-existent fields — return default.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except AttributeError:
        return default


class CUCMSourceAdapter(Adapter):
    """DiffSync adapter that loads CUCM state via AXL."""

    phone_system = PhoneSystemModel
    partition = PartitionModel
    calling_search_space = CallingSearchSpaceModel
    css_partition_membership = CSSPartitionMembershipModel
    directory_number = DirectoryNumberModel
    phone = PhoneModel
    line = LineModel
    speed_dial = SpeedDialModel
    busy_lamp_field = BusyLampFieldModel
    phone_service_url = PhoneServiceUrlModel
    trunk = TrunkModel
    route_list = RouteListModel
    route_group = RouteGroupModel
    route_pattern = RoutePatternModel
    translation_pattern = TranslationPatternModel
    analog_gateway = AnalogGatewayModel
    analog_port = AnalogPortModel

    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "css_partition_membership",
        "directory_number",
        "phone",
        "line",
        "speed_dial",
        "busy_lamp_field",
        "phone_service_url",
        "trunk",
        "route_list",
        "route_group",
        "route_pattern",
        "translation_pattern",
        "analog_gateway",
        "analog_port",
    )

    type = "cisco-ucm"

    # CUCM models a "null partition" as an absent routePartitionName ref.
    # We synthesize a Partition record under this name so DiffSync has
    # something concrete to point partition-less DNs/patterns at.
    NULL_PARTITION_NAME = "(none)"

    def __init__(
        self,
        *args,
        client,
        phone_system_record,
        ris_client=None,
        job=None,
        enrich_phone_lines=False,
        enrich_phone_ip=False,
        **kwargs,
    ):
        """Take a configured AXLClient and the PhoneSystem record it belongs to.

        `phone_system_record` is the Nautobot PhoneSystem ORM instance —
        we need its name + version for the synthetic phone_system DiffSync
        record we emit (CUCM doesn't have a "phone system" object; the
        cluster IS the system).

        `enrich_phone_lines` enables per-phone getPhone calls to populate
        the Line records (button index, DN reference, label). Off by
        default since it's slow — ~200-400ms per phone. For 1000+ phones
        this adds 5-10 minutes to the sync.
        """
        super().__init__(*args, **kwargs)
        self.client = client
        self.ris_client = ris_client
        self.phone_system_record = phone_system_record
        self.job = job
        self.enrich_phone_lines = enrich_phone_lines
        self.enrich_phone_ip = enrich_phone_ip
        # Populated by _fetch_ris_data when enrich_phone_ip=True. Maps CUCM
        # device-name (e.g. "SEPCAFEBABE0001") to the full RIS dict — IP,
        # status, active/inactive load, login user, status reason. None for
        # phones that didn't register in the RIS time window.
        self._ris_map: dict[str, dict] = {}
        # Timestamp of the most recent RIS poll — used to populate Phone's
        # `live_status_polled_at` so operators know when "ActiveLoadID =
        # Webex 46.4.0" was actually true.
        self._ris_polled_at = None
        # When enrich_phone_lines is off, exclude all per-phone button models
        # (Line, SpeedDial, PhoneServiceUrl) from the diff so existing
        # records in Nautobot aren't wiped. Job pairs this with the same
        # exclusion on the destination adapter.
        if not enrich_phone_lines:
            _button_models = {"line", "speed_dial", "phone_service_url"}
            self.top_level = tuple(t for t in self.top_level if t not in _button_models)

    def _resolve_partition(self, ref: Any) -> str:
        """Pull the partition name out of a routePartitionName ref.

        AXL returns these as XFkType objects with `_value_1` carrying the
        actual name — None when the record has no partition assigned.
        Map None/empty to NULL_PARTITION_NAME so downstream DiffSync sees
        a concrete identifier.
        """
        if ref is None:
            return self.NULL_PARTITION_NAME
        name = _get(ref, "_value_1", "") or ""
        return name if name else self.NULL_PARTITION_NAME

    def load(self) -> None:
        """Walk AXL listX operations and populate DiffSync models.

        v1 limitations: RoutePattern + AnalogGateway require per-record
        getX calls for target/protocol fields (listX returns scalars
        only). Skipping them in v1 — the partial data they'd produce
        violates our DB constraints (RoutePattern XOR check). Future
        enrichment phase can add the getX two-step.
        """
        ps = self.phone_system_record
        self.add(self.phone_system(
            name=ps.name,
            vendor=ps.vendor,
            version=ps.version,
            hostname=ps.hostname,
        ))

        self._load_partitions(ps.name)
        self._load_calling_search_spaces(ps.name)
        self._load_directory_numbers(ps.name)
        if self.enrich_phone_ip and self.ris_client is not None:
            self._fetch_ris_data()
        self._load_phones_and_lines(ps.name)
        self._load_trunks(ps.name)
        self._load_route_lists(ps.name)
        self._load_route_groups(ps.name)
        self._load_route_patterns(ps.name)  # uses getRoutePattern for target resolution
        self._load_translation_patterns(ps.name)
        self._load_gateways_and_ports(ps.name)

    # -- Per-collection loaders ----------------------------------------------

    def _load_partitions(self, ps_name: str) -> None:
        for row in self.client.list_route_partitions():
            self.add(self.partition(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                description=_get(row, "description", "") or "",
            ))
        # Add the synthetic null-partition so partition-less DNs/patterns
        # have a concrete partition identifier to point at.
        self.add(self.partition(
            name=self.NULL_PARTITION_NAME,
            phone_system__name=ps_name,
            description="Synthetic placeholder for CUCM lines/patterns with no explicit partition.",
        ))

    def _load_calling_search_spaces(self, ps_name: str) -> None:
        css_rows = self.client.list_css()
        for row in css_rows:
            self.add(self.calling_search_space(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                description=_get(row, "description", "") or "",
            ))
        # Per-CSS getCss enrichment for partition memberships. listCss only
        # returns scalar fields (no `members` element); the membership
        # association lives only in getCss. ~16 CSSes per typical cluster
        # makes this cheap (~3-5s) so it's always-on rather than gated by
        # an opt-in flag.
        for row in css_rows:
            css_name = _get(row, "name", "")
            if not css_name:
                continue
            try:
                full = getattr(self.client._service.getCss(name=css_name), "return").css
            except Exception:
                continue  # one bad CSS shouldn't blow up the whole sync
            members_obj = _get(full, "members")
            member_arr = _get(members_obj, "member") or [] if members_obj else []
            for member in member_arr:
                rp = _get(member, "routePartitionName")
                part_name = _get(rp, "_value_1") if rp else None
                if not part_name:
                    part_name = self.NULL_PARTITION_NAME
                idx = _get(member, "index", 1)
                try:
                    priority = int(idx) if idx is not None else 1
                except (TypeError, ValueError):
                    priority = 1
                self.add(self.css_partition_membership(
                    css__phone_system__name=ps_name,
                    css__name=css_name,
                    partition__name=part_name,
                    priority=priority,
                ))

    def _load_directory_numbers(self, ps_name: str) -> None:
        for row in self.client.list_lines():
            partition_name = self._resolve_partition(_get(row, "routePartitionName"))
            self.add(self.directory_number(
                extension=_get(row, "pattern", ""),
                partition__name=partition_name,
                partition__phone_system__name=ps_name,
                alerting_name=_get(row, "alertingName", "") or "",
                voicemail_profile=_get(_get(row, "voiceMailProfileName"), "_value_1", "") or "",
                vendor_extras=_extract_extras(row, exclude={"pattern", "routePartitionName", "alertingName"}),
            ))

    # Device-name prefix → device_kind value. Anything not in this dict is
    # currently out of scope (CTI ports, gateway-side analog phones land in
    # follow-up phases with their own model semantics).
    _PHONE_KINDS_BY_PREFIX = {
        "SEP": "sep",  # Physical IP phones — real MAC, full hardware
        "CSF": "csf",  # Cisco Jabber Desktop (Windows/Mac)
        "TCT": "tct",  # Cisco Jabber for iPhone/iPad
        "BOT": "bot",  # Cisco Jabber for Android
        "CSK": "csk",  # CSF variant
        "ATA": "ata",  # Cisco ATA-19x analog terminal adapter
    }

    def _load_phones_and_lines(self, ps_name: str) -> None:
        skipped_non_phone = 0
        sep_devices: list[tuple[str, Any]] = []  # (device_name, listPhone-row) for enrichment phase
        for phone_row in self.client.list_phones():
            device_name = _get(phone_row, "name", "") or ""

            # Dispatch on device_name prefix. SEP/ATA encode a real MAC in the
            # name (15 chars: 3-letter prefix + 12 hex MAC). CSF/TCT/BOT/CSK
            # encode a username (variable length). Anything else (CCX, CER,
            # CTI, AN4) is out of scope for v1 — they're CTI ports or gateway
            # analog phones, conceptually different from "phone endpoints"
            # and modeled separately.
            prefix = device_name[:3] if len(device_name) >= 3 else ""
            kind = self._PHONE_KINDS_BY_PREFIX.get(prefix)
            if kind is None:
                skipped_non_phone += 1
                continue

            mac_formatted = None
            if kind in ("sep", "ata") and len(device_name) == 15:
                # Hardware endpoints: trailing 12 chars = MAC. Format as
                # canonical aa:bb:cc:dd:ee:ff for storage.
                mac = device_name[3:].lower()
                mac_formatted = ":".join(mac[i:i + 2] for i in range(0, len(mac), 2))
            sep_devices.append((device_name, phone_row))

            # Pull live-status fields from the RIS map (populated when
            # enrich_phone_ip=True). All keys default to empty/None when this
            # phone wasn't seen in the RIS time window, so phones can keep
            # blank live-status fields without us having to special-case here.
            ris = self._ris_map.get(device_name, {})
            ip = (ris.get("ip_address") or "").strip() or None
            ris_status = (ris.get("status") or "").strip().lower()
            # Map RIS status strings to our RegistrationStatusChoices set.
            # RIS reports "Registered", "UnRegistered", "Rejected", "Unknown",
            # "PartiallyRegistered". Anything else stays "unknown".
            ris_status_map = {
                "registered": "registered",
                "unregistered": "unregistered",
                "partiallyregistered": "partially_registered",
            }
            registration = ris_status_map.get(ris_status.replace(" ", ""),
                                              _get(phone_row, "currentRegistrationStatus", "unknown") or "unknown")
            # FK fields (Device Pool, CSS, security/SIP profiles, etc.) come
            # back as {_value_1: "Name", uuid: "..."}. Resolve to plain names.
            def _fk_name(field_name):
                ref = _get(phone_row, field_name)
                if not ref:
                    return ""
                v = _get(ref, "_value_1", "") or ""
                # CCM uses the literal string "None" for empty FKs — treat as blank
                return "" if v == "None" else v

            axl_model = _get(phone_row, "model", "") or ""
            extras = _extract_extras(phone_row, exclude={
                "name", "description", "currentRegistrationStatus",
                "model",  # excluded — re-added explicitly below as axl_model so
                          # the device-creation pass can find/create the right DeviceType
                "locationName", "networkLocation",
                "devicePoolName", "commonPhoneConfigName", "commonDeviceConfigName",
                "phoneTemplateName", "softkeyTemplateName",
                "ownerUserName", "mobilityUserIdName",
                "builtInBridgeStatus", "callInfoPrivacyStatus", "deviceMobilityMode",
                "alwaysUsePrimeLine", "alwaysUsePrimeLineForVoiceMessage",
                "userLocale", "networkLocale", "aarNeighborhoodName",
                "dndStatus", "dndOption",
                "securityProfileName", "sipProfileName",
                "rerouteCallingSearchSpaceName", "subscribeCallingSearchSpaceName",
                "mtpRequired", "packetCaptureMode",
            })
            extras["axl_model"] = axl_model  # stash for post-sync device-creation

            self.add(self.phone(
                device_name=device_name,
                phone_system__name=ps_name,
                mac_address=mac_formatted,
                device_kind=kind,
                description=_get(phone_row, "description", "") or "",
                registration_status=registration,
                last_registered_ip=ip,
                # Live status from RisPort70 (only present when enrich_phone_ip=True)
                active_load=(ris.get("active_load") or "").strip(),
                inactive_load=(ris.get("inactive_load") or "").strip(),
                live_login_user=(ris.get("login_user_id") or "").strip(),
                status_reason=(ris.get("status_reason") or "").strip(),
                live_status_polled_at=self._ris_polled_at,
                # CCM Location (Call Admission Control) + Network Location
                ccm_location=_fk_name("locationName"),
                network_location=(_get(phone_row, "networkLocation", "") or ""),
                # Device Information
                device_pool=_fk_name("devicePoolName"),
                common_phone_profile=_fk_name("commonPhoneConfigName"),
                common_device_configuration=_fk_name("commonDeviceConfigName"),
                phone_button_template=_fk_name("phoneTemplateName"),
                softkey_template=_fk_name("softkeyTemplateName"),
                owner_user_id=_fk_name("ownerUserName"),
                mobility_user_id=_fk_name("mobilityUserIdName"),
                built_in_bridge=(_get(phone_row, "builtInBridgeStatus", "") or ""),
                privacy=(_get(phone_row, "callInfoPrivacyStatus", "") or ""),
                device_mobility_mode=(_get(phone_row, "deviceMobilityMode", "") or ""),
                always_use_prime_line=(_get(phone_row, "alwaysUsePrimeLine", "") or ""),
                always_use_prime_line_for_voice=(_get(phone_row, "alwaysUsePrimeLineForVoiceMessage", "") or ""),
                user_locale=(_get(phone_row, "userLocale", "") or ""),
                network_locale=(_get(phone_row, "networkLocale", "") or ""),
                aar_neighborhood=_fk_name("aarNeighborhoodName"),
                dnd_status=_axl_bool(_get(phone_row, "dndStatus")),
                dnd_option=(_get(phone_row, "dndOption", "") or ""),
                # Protocol Specific Information
                device_security_profile=_fk_name("securityProfileName"),
                sip_profile=_fk_name("sipProfileName"),
                rerouting_css=_fk_name("rerouteCallingSearchSpaceName"),
                subscribe_css=_fk_name("subscribeCallingSearchSpaceName"),
                mtp_required=_axl_bool(_get(phone_row, "mtpRequired")),
                packet_capture_mode=(_get(phone_row, "packetCaptureMode", "") or ""),
                # Long-tail
                vendor_extras=extras,
            ))

            # Lines are nested children of the phone.
            lines_container = _get(phone_row, "lines")
            for line in _get(lines_container, "line", []) or []:
                dirn = _get(line, "dirn")
                if dirn is None:
                    continue
                dn_pattern = _get(dirn, "pattern", "")
                dn_partition_ref = _get(dirn, "routePartitionName")
                dn_partition_name = _get(dn_partition_ref, "_value_1", "") if dn_partition_ref else ""
                self.add(self.line(
                    phone__device_name=device_name,
                    phone__phone_system__name=ps_name,
                    button_index=int(_get(line, "index", 0) or 0),
                    directory_number__extension=dn_pattern,
                    directory_number__partition__name=dn_partition_name,
                    label=(_get(line, "label", "") or _get(line, "displayAscii", "") or _get(line, "display", "") or ""),
                    ring_setting=_get(line, "ringSetting", "") or "",
                ))

        if skipped_non_phone and self.job:
            self.job.logger.info(f"Skipped {skipped_non_phone} non-phone records (CTI ports, gateway-attached analog phones — modeled separately)")

        # Optional second-phase: per-phone getPhone to populate line membership.
        # Slow — ~200-400ms per call, so this is off by default.
        if self.enrich_phone_lines:
            self._enrich_lines(ps_name, sep_devices)

    def _fetch_ris_data(self) -> None:
        """Pull live registration data from RisPort70 into _ris_map.

        Single bulk call (auto-paginated) — much cheaper than per-phone
        getPhone. Only used when enrich_phone_ip=True. Errors are logged
        but non-fatal: phones just keep their live-status fields blank.

        Captures: IP, status, ActiveLoadID (running firmware/Webex build),
        InactiveLoadID (rollback target), LoginUserId (currently signed-in
        user), StatusReason (why this status). All sourced from the same
        RIS response so there's no extra cost vs the previous IP-only fetch.
        """
        from datetime import datetime, timezone
        if self.job:
            self.job.logger.info("Fetching live registration data from RisPort70...")
        try:
            devices = self.ris_client.select_phones(status="Any")
        except Exception as e:  # noqa: BLE001
            if self.job:
                self.job.logger.warning(f"  RisPort fetch failed: {type(e).__name__}: {e}")
            return
        self._ris_polled_at = datetime.now(timezone.utc)
        for dev in devices:
            name = (dev.get("name") or "").strip()
            if not name:
                continue
            self._ris_map[name] = dev  # full dict — caller indexes into it
        if self.job:
            with_loads = sum(1 for d in self._ris_map.values() if (d.get("active_load") or "").strip())
            self.job.logger.info(
                f"  RisPort returned {len(self._ris_map)} devices "
                f"({with_loads} with ActiveLoadID — running firmware/Webex builds)"
            )

    def _enrich_lines(self, ps_name: str, sep_devices: list) -> None:
        """Walk each SEP* phone via getPhone to pull all four button-type arrays.

        getPhone returns the four button categories — lines, speed dials,
        BLFs, and service URLs — as nested arrays in a single response,
        so one call enriches all four at once. We also pull per-line
        enrichment fields (max calls, busy trigger, MWI policy, etc.) from
        lines.line[*] which aren't present in the bulk listPhone response.
        """
        total = len(sep_devices)
        if self.job:
            self.job.logger.info(f"Enriching {total} phones with line/speed-dial/BLF/service data (this may take several minutes)...")
        for idx, (device_name, _) in enumerate(sep_devices):
            if self.job and idx and idx % 100 == 0:
                self.job.logger.info(f"  Enriched {idx}/{total} phones...")
            try:
                phone_obj = self.client.get_phone(device_name)
            except Exception as e:  # noqa: BLE001 — log + skip; one bad record shouldn't kill the sync
                if self.job:
                    self.job.logger.warning(f"  getPhone({device_name!r}) failed: {type(e).__name__}: {e}")
                continue
            if phone_obj is None:
                continue
            # Lines (DN appearances) — with per-line enrichment fields
            lines_container = _get(phone_obj, "lines")
            line_arr = _get(lines_container, "line", []) or []
            for line in line_arr:
                dirn = _get(line, "dirn")
                if dirn is None:
                    continue
                dn_pattern = _get(dirn, "pattern", "")
                rp_ref = _get(dirn, "routePartitionName")
                dn_partition_name = self._resolve_partition(rp_ref)

                def _int_or_none(v):
                    """Coerce '4' / 4 / '' / None → int or None."""
                    if v in (None, "", 0, "0"):
                        return None
                    try:
                        return int(v)
                    except (TypeError, ValueError):
                        return None

                self.add(self.line(
                    phone__device_name=device_name,
                    phone__phone_system__name=ps_name,
                    button_index=int(_get(line, "index", 0) or 0),
                    directory_number__extension=dn_pattern,
                    directory_number__partition__name=dn_partition_name,
                    label=(_get(line, "label", "") or _get(line, "displayAscii", "") or _get(line, "display", "") or ""),
                    ring_setting=_get(line, "ringSetting", "") or "",
                    # Per-line enrichment
                    max_num_calls=_int_or_none(_get(line, "maxNumCalls")),
                    busy_trigger=_int_or_none(_get(line, "busyTrigger")),
                    mwl_policy=(_get(line, "mwlPolicy", "") or ""),
                    audible_mwi=(_get(line, "audibleMwi", "") or ""),
                    recording_flag=(_get(line, "recordingFlag", "") or ""),
                    missed_call_logging=_axl_bool(_get(line, "missedCallLogging")),
                    partition_usage=(_get(line, "partitionUsage", "") or ""),
                    consecutive_ring_setting=(_get(line, "consecutiveRingSetting", "") or ""),
                    ring_setting_idle_pickup_alert=(_get(line, "ringSettingIdlePickupAlert", "") or ""),
                    ring_setting_active_pickup_alert=(_get(line, "ringSettingActivePickupAlert", "") or ""),
                ))
            # Speed dials — `dirn` here is a plain string (the destination
            # number), unlike Line's `dirn` which is a complex DN reference.
            sd_container = _get(phone_obj, "speeddials")
            sd_arr = _get(sd_container, "speeddial", []) or []
            for sd in sd_arr:
                number = _get(sd, "dirn", "") or ""
                if not number:
                    continue
                self.add(self.speed_dial(
                    phone__device_name=device_name,
                    phone__phone_system__name=ps_name,
                    button_index=int(_get(sd, "index", 0) or 0),
                    number=str(number),
                    label=_get(sd, "label", "") or "",
                ))
            # BLFs — speed-dial buttons with watched-destination presence indication.
            # AXL field name on the BLF object is `blfDest` (the watched number);
            # `index` is the button position; `asteriskService` indicates whether
            # the BLF doubles as a * speed-dial.
            blf_container = _get(phone_obj, "busyLampFields")
            blf_arr = _get(blf_container, "busyLampField", []) or []
            for blf in blf_arr:
                dest = _get(blf, "blfDest", "") or ""
                if not dest:
                    continue
                self.add(self.busy_lamp_field(
                    phone__device_name=device_name,
                    phone__phone_system__name=ps_name,
                    button_index=int(_get(blf, "index", 0) or 0),
                    destination=str(dest),
                    label=_get(blf, "label", "") or "",
                    asterisk_service=_axl_bool(_get(blf, "asteriskService")),
                ))
            # Service URLs — XML services (Extension Mobility, custom apps).
            # Some clusters configure multiple service URLs without setting
            # `urlButtonIndex` (or set them all to 0 when the buttons aren't
            # actually phone buttons but background services). Fall back to
            # the array position so we don't collide on (phone, button_index).
            svc_container = _get(phone_obj, "services")
            svc_arr = _get(svc_container, "service", []) or []
            for pos, svc in enumerate(svc_arr):
                url = _get(svc, "url", "") or ""
                if not url:
                    continue
                explicit_idx = _get(svc, "urlButtonIndex")
                idx = int(explicit_idx) if explicit_idx not in (None, "", 0, "0") else pos
                self.add(self.phone_service_url(
                    phone__device_name=device_name,
                    phone__phone_system__name=ps_name,
                    button_index=idx,
                    url=str(url),
                    label=_get(svc, "label", "") or "",
                ))

    def _load_route_lists(self, ps_name: str) -> None:
        for row in self.client.list_route_lists():
            self.add(self.route_list(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                description=_get(row, "description", "") or "",
            ))

    def _load_route_groups(self, ps_name: str) -> None:
        for row in self.client.list_route_groups():
            algo = (_get(row, "distributionAlgorithm", "top_down") or "top_down").lower()
            # CCM uses "Top Down" / "Circular" — normalize to our enum.
            algo_map = {"top down": "top_down", "topdown": "top_down", "circular": "circular"}
            self.add(self.route_group(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                distribution_algorithm=algo_map.get(algo, "top_down"),
                description=_get(row, "description", "") or "",
            ))

    def _load_trunks(self, ps_name: str) -> None:
        for row in self.client.list_sip_trunks():
            destinations = _get(row, "destinations")
            dest_list = _get(destinations, "destination", []) or []
            first_dest = dest_list[0] if dest_list else None
            self.add(self.trunk(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                trunk_type="sip",
                destination_address=_get(first_dest, "addressIpv4", "") or "",
                destination_port=_get(first_dest, "port") if first_dest else None,
                vendor_extras=_extract_extras(row, exclude={"name", "destinations"}),
            ))

    def _load_route_patterns(self, ps_name: str) -> None:
        # Two-phase: listRoutePattern for IDs/scalars, getRoutePattern per
        # record to resolve the destination element. listX doesn't expose
        # destination at all — it's only available via getX. ~165 patterns
        # per typical cluster makes this ~30s. Patterns whose destination
        # resolves to neither a RouteList nor a Gateway are skipped (the
        # XOR check constraint requires exactly one target).
        for row in self.client.list_route_patterns():
            uuid = _get(row, "uuid")
            if not uuid:
                continue
            try:
                full = getattr(self.client._service.getRoutePattern(uuid=uuid), "return").routePattern
            except Exception:
                continue
            pattern = _get(full, "pattern", "")
            if not pattern:
                continue
            partition_name = self._resolve_partition(_get(full, "routePartitionName"))
            urgent_raw = _get(full, "patternUrgency", "false")
            urgent = str(urgent_raw).lower() in ("true", "1", "yes")
            dest = _get(full, "destination")
            rln = _get(dest, "routeListName") if dest else None
            target_route_list = _get(rln, "_value_1") if rln else None
            gn = _get(dest, "gatewayName") if dest else None
            target_trunk = _get(gn, "_value_1") if gn else None
            if not target_route_list and not target_trunk:
                continue  # no resolvable target — skip rather than violate the XOR constraint
            css_ref = _get(full, "callingSearchSpaceName")
            css_name = _get(css_ref, "_value_1") if css_ref else None
            self.add(self.route_pattern(
                pattern=pattern,
                partition__name=partition_name,
                partition__phone_system__name=ps_name,
                urgent=urgent,
                discard_digits=_get(full, "discardDigits", "") or "",
                target_trunk__name=target_trunk,
                target_route_list__name=target_route_list,
                css__name=css_name,
            ))

    def _load_translation_patterns(self, ps_name: str) -> None:
        """Translation patterns rewrite digits and re-route — no destination FK.

        listTransPattern returns the full Pattern Definition + Calling/Called
        Party Transformation field set in scalars (no per-record getX needed).
        We surface the operationally-important fields as explicit columns
        and drop the long-tail dropdowns (presentation bits, numbering plans,
        number types) into vendor_extras for fidelity.
        """
        # Fields that get explicit columns — exclude them from vendor_extras
        # so we don't double-store. The remaining AXL fields (presentation
        # bits, numbering plans, etc.) flow through to vendor_extras.
        EXPLICIT = {
            "pattern", "description", "routePartitionName", "callingSearchSpaceName",
            "blockEnable", "releaseClause", "patternUrgency", "provideOutsideDialtone",
            "useOriginatorCss", "dontWaitForIDTOnSubsequentHops", "routeNextHopByCgpn",
            "isEmergencyServiceNumber", "routeClass",
            "useCallingPartyPhoneMask", "callingPartyTransformationMask",
            "callingPartyPrefixDigits",
            "digitDiscardInstructionName", "calledPartyTransformationMask",
            "prefixDigitsOut",
        }
        for row in self.client.list_translation_patterns():
            pattern = _get(row, "pattern", "")
            if not pattern:
                continue
            partition_name = self._resolve_partition(_get(row, "routePartitionName"))
            css_ref = _get(row, "callingSearchSpaceName")
            css_name = _get(css_ref, "_value_1") if css_ref else None
            ddi_ref = _get(row, "digitDiscardInstructionName")
            ddi_name = _get(ddi_ref, "_value_1", "") if ddi_ref else ""
            self.add(self.translation_pattern(
                pattern=pattern,
                partition__name=partition_name,
                partition__phone_system__name=ps_name,
                description=_get(row, "description", "") or "",
                css__name=css_name,
                # Pattern Definition
                block_enable=_axl_bool(_get(row, "blockEnable")),
                release_clause=(_get(row, "releaseClause", "") or ""),
                urgent_priority=_axl_bool(_get(row, "patternUrgency")),
                provide_outside_dial_tone=_axl_bool(_get(row, "provideOutsideDialtone")),
                use_originator_css=_axl_bool(_get(row, "useOriginatorCss")),
                dont_wait_for_idt=_axl_bool(_get(row, "dontWaitForIDTOnSubsequentHops")),
                route_next_hop_by_cgpn=_axl_bool(_get(row, "routeNextHopByCgpn")),
                is_emergency_service_number=_axl_bool(_get(row, "isEmergencyServiceNumber")),
                route_class=(_get(row, "routeClass", "") or ""),
                # Calling Party Transformations
                use_calling_party_phone_mask=(_get(row, "useCallingPartyPhoneMask", "") or ""),
                calling_party_transformation_mask=(_get(row, "callingPartyTransformationMask", "") or ""),
                calling_party_prefix_digits=(_get(row, "callingPartyPrefixDigits", "") or ""),
                # Called Party Transformations
                digit_discard_instruction=(ddi_name or ""),
                called_party_transformation_mask=(_get(row, "calledPartyTransformationMask", "") or ""),
                prefix_digits_out=(_get(row, "prefixDigitsOut", "") or ""),
                # Long-tail (presentation bits, numbering plans, types)
                vendor_extras=_extract_extras(row, exclude=EXPLICIT),
            ))

    def _load_gateways_and_ports(self, ps_name: str) -> None:
        """Sync analog gateways and the AN4-derived FXS port-DN bindings.

        Two-phase:

          1. listGateway → AnalogGateway records. NB: listGateway returns
             gateways under the field `domainName`, NOT `name`. Earlier
             code used the wrong field which silently produced empty-string
             identifiers and zero records. We also call getGateway per row
             to capture the unit/subunit hierarchy (module count, FXS
             port count) into vendor_extras.

          2. listPhone(name=AN4%) → AnalogPort records. CCM models analog
             phones as AN4-prefix Phone records; their device-name encodes
             gateway-suffix + port-hex. We parse that, look up the gateway
             by suffix, getPhone to fetch the line/DN binding, and emit
             one AnalogPort per record.
        """
        # Phase 1: gateways (with getGateway enrichment for unit info)
        gateways_by_suffix: dict[str, str] = {}  # suffix → gateway_name
        for row in self.client.list_gateways():
            gw_name = _get(row, "domainName", "") or ""
            if not gw_name:
                continue
            # Pull deeper detail via getGateway — the unit/subunit array
            # tells us module count + FXS port capacity. Wrapped in try so
            # one bad gateway doesn't kill the loop.
            unit_summary: list[dict] = []
            try:
                full = self._service_get_gateway(gw_name)
                gw_full = _get(_get(full, "return"), "gateway") if full else None
                units = _get(gw_full, "units")
                unit_arr = _get(units, "unit", []) or []
                if not isinstance(unit_arr, list):
                    unit_arr = [unit_arr]
                for u in unit_arr:
                    subs = _get(u, "subunits")
                    sub_arr = _get(subs, "subunit", []) or []
                    if not isinstance(sub_arr, list):
                        sub_arr = [sub_arr]
                    for s in sub_arr:
                        unit_summary.append({
                            "unit_index": _get(u, "index"),
                            "unit_product": _get(u, "product"),
                            "subunit_index": _get(s, "index"),
                            "subunit_product": _get(s, "product"),
                            "begin_port": _get(s, "beginPort"),
                        })
            except Exception:  # noqa: BLE001
                pass

            extras = _extract_extras(row, exclude={"domainName", "product", "protocol"})
            extras["module_units"] = unit_summary

            self.add(self.analog_gateway(
                name=gw_name,
                phone_system__name=ps_name,
                model=_get(row, "product", "") or "",
                protocol=(_get(row, "protocol", "mgcp") or "mgcp").lower(),
                vendor_extras=extras,
            ))
            # Build suffix → name map for AN4 lookup. Gateway names follow
            # convention <SITE>GW<MAC-suffix> (e.g. "SKIGW4FB1F0C501") and
            # AN4 device names use the same suffix. Match by trailing 9 chars.
            if len(gw_name) >= 9:
                gateways_by_suffix[gw_name[-9:].upper()] = gw_name

        if not gateways_by_suffix:
            return  # no gateways → no ports to sync

        # Phase 2: AN4 records → AnalogPort. Pull all AN4* phones at once,
        # then per-record getPhone for the line/DN binding.
        an4_rows = self.client._list(
            "listPhone", "phone",
            search_criteria={"name": "AN4%"},
            returned_tags={"name": "", "description": ""},
        )
        for an4 in an4_rows:
            device_name = _get(an4, "name", "") or ""
            # AN4 + 9-char-MAC + 3-char-port-hex = 15 chars exactly
            if not device_name.startswith("AN4") or len(device_name) != 15:
                continue
            mac_suffix = device_name[3:12].upper()
            port_hex = device_name[12:15]
            gw_name = gateways_by_suffix.get(mac_suffix)
            if gw_name is None:
                continue  # AN4 references a gateway we don't have

            try:
                port_index = int(port_hex, 16)
            except ValueError:
                continue

            # Lookup the bound DN via getPhone
            try:
                full = self.client.get_phone(device_name)
            except Exception:  # noqa: BLE001
                continue
            dn_extension = None
            dn_partition_name = None
            lines = _get(_get(full, "lines"), "line", []) or []
            if not isinstance(lines, list):
                lines = [lines]
            if lines:
                dirn = _get(lines[0], "dirn")
                if dirn:
                    dn_extension = _get(dirn, "pattern", "") or None
                    rp_ref = _get(dirn, "routePartitionName")
                    dn_partition_name = self._resolve_partition(rp_ref) if rp_ref else None

            self.add(self.analog_port(
                gateway__name=gw_name,
                gateway__phone_system__name=ps_name,
                port_index=port_index,
                port_type="fxs",  # AN4 phones are always on FXS ports
                directory_number__extension=dn_extension,
                directory_number__partition__name=dn_partition_name,
            ))

    def _service_get_gateway(self, name: str):
        """Wrapper for getGateway — returns the raw zeep response.

        Stays lightweight — caller uses _get() for tolerant attribute access.
        """
        try:
            return self.client._service.getGateway(domainName=name)
        except Exception:  # noqa: BLE001
            return None


def _extract_extras(obj: Any, exclude: set[str]) -> dict:
    """Pull all non-excluded fields off an AXL object into a flat dict.

    Used to populate `vendor_extras` for fields we don't model as columns.
    Keys with None values are dropped.
    """
    extras: dict = {}
    if obj is None:
        return extras
    # Try dict-like first (zeep sometimes returns dicts)
    if hasattr(obj, "items"):
        items = obj.items()
    else:
        items = vars(obj).items() if hasattr(obj, "__dict__") else []
    for key, value in items:
        if key in exclude or key.startswith("_"):
            continue
        if value is None or value == "":
            continue
        if isinstance(value, (str, int, float, bool, list, dict)):
            extras[key] = value
    return extras
