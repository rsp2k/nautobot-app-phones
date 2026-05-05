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
    CallingSearchSpaceModel,
    CSSPartitionMembershipModel,
    DirectoryNumberModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneSystemModel,
    RouteGroupModel,
    RouteListModel,
    RoutePatternModel,
    TrunkModel,
)


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
    trunk = TrunkModel
    route_list = RouteListModel
    route_group = RouteGroupModel
    route_pattern = RoutePatternModel
    analog_gateway = AnalogGatewayModel

    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "css_partition_membership",
        "directory_number",
        "phone",
        "line",
        "trunk",
        "route_list",
        "route_group",
        "route_pattern",
        # analog_gateway deferred until we add per-record getGateway enrichment
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
        # Populated by _fetch_ris_data when enrich_phone_ip=True; map of
        # CUCM device-name (e.g. "SEPCAFEBABE0001") to IP address string.
        self._ip_map: dict[str, str] = {}
        # When enrich_phone_lines is off, exclude `line` from the diff so
        # existing Line records in Nautobot aren't wiped by the sync. The
        # Job pairs this with the same exclusion on the destination adapter.
        if not enrich_phone_lines:
            self.top_level = tuple(t for t in self.top_level if t != "line")

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
        # self._load_gateways(ps.name)        # v2 — needs getGateway enrichment

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

    def _load_phones_and_lines(self, ps_name: str) -> None:
        skipped_non_sep = 0
        sep_devices: list[tuple[str, Any]] = []  # (device_name, listPhone-row) for enrichment phase
        for phone_row in self.client.list_phones():
            device_name = _get(phone_row, "name", "") or ""

            # CUCM phones come in many flavors: SEP* (physical), CSF*/TCT*/
            # TAB* (softphones), BOT* (bots), CER-CTI-* (Emergency Responder
            # CTI ports). Only SEP* devices have real MAC addresses. v1 syncs
            # only the physical phones; softphones/CTI ports can land in a
            # future phase with a synthetic-MAC scheme or a relaxed schema.
            if not device_name.startswith("SEP") or len(device_name) != 15:
                skipped_non_sep += 1
                continue
            mac = device_name.removeprefix("SEP").lower()
            mac_formatted = ":".join(mac[i:i + 2] for i in range(0, len(mac), 2))
            sep_devices.append((device_name, phone_row))

            ip = self._ip_map.get(device_name) or None
            self.add(self.phone(
                mac_address=mac_formatted,
                phone_system__name=ps_name,
                device_name=device_name,
                model=_get(phone_row, "model", "") or "",
                registration_status=_get(phone_row, "currentRegistrationStatus", "unknown") or "unknown",
                last_registered_ip=ip,
                vendor_extras=_extract_extras(phone_row, exclude={"name", "model", "currentRegistrationStatus"}),
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

        if skipped_non_sep and self.job:
            self.job.logger.info(f"Skipped {skipped_non_sep} non-SEP phone records (softphones/CTI ports)")

        # Optional second-phase: per-phone getPhone to populate line membership.
        # Slow — ~200-400ms per call, so this is off by default.
        if self.enrich_phone_lines:
            self._enrich_lines(ps_name, sep_devices)

    def _fetch_ris_data(self) -> None:
        """Pull live registration/IP data from RisPort70 into _ip_map.

        Single bulk call (auto-paginated) — much cheaper than per-phone
        getPhone. Only used when enrich_phone_ip=True. Errors are logged
        but non-fatal: phones just keep their IP=None.
        """
        if self.job:
            self.job.logger.info("Fetching live registration data from RisPort70...")
        try:
            devices = self.ris_client.select_phones(status="Any")
        except Exception as e:  # noqa: BLE001
            if self.job:
                self.job.logger.warning(f"  RisPort fetch failed: {type(e).__name__}: {e}")
            return
        for dev in devices:
            ip = (dev.get("ip_address") or "").strip()
            name = dev.get("name") or ""
            if name and ip:
                self._ip_map[name] = ip
        if self.job:
            self.job.logger.info(f"  RisPort returned {len(self._ip_map)} phones with IPs")

    def _enrich_lines(self, ps_name: str, sep_devices: list) -> None:
        """Walk each SEP* phone via getPhone to pull its lines + DN refs."""
        total = len(sep_devices)
        if self.job:
            self.job.logger.info(f"Enriching {total} phones with line data (this may take several minutes)...")
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
            lines_container = _get(phone_obj, "lines")
            line_arr = _get(lines_container, "line", []) or []
            for line in line_arr:
                dirn = _get(line, "dirn")
                if dirn is None:
                    continue
                dn_pattern = _get(dirn, "pattern", "")
                rp_ref = _get(dirn, "routePartitionName")
                dn_partition_name = self._resolve_partition(rp_ref)
                self.add(self.line(
                    phone__device_name=device_name,
                    phone__phone_system__name=ps_name,
                    button_index=int(_get(line, "index", 0) or 0),
                    directory_number__extension=dn_pattern,
                    directory_number__partition__name=dn_partition_name,
                    label=(_get(line, "label", "") or _get(line, "displayAscii", "") or _get(line, "display", "") or ""),
                    ring_setting=_get(line, "ringSetting", "") or "",
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

    def _load_gateways(self, ps_name: str) -> None:
        for row in self.client.list_gateways():
            self.add(self.analog_gateway(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                model=_get(row, "product", "") or "",
                protocol=(_get(row, "protocol", "mgcp") or "mgcp").lower(),
                vendor_extras=_extract_extras(row, exclude={"name", "product", "protocol"}),
            ))


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
