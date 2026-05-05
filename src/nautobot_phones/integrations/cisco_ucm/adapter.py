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
    DirectoryNumberModel,
    LineModel,
    PartitionModel,
    PhoneModel,
    PhoneSystemModel,
    RoutePatternModel,
    TrunkModel,
)


def _get(obj: Any, name: str, default=None) -> Any:
    """Tolerant attribute access for AXL response objects.

    AXL/zeep return objects look like Pydantic-ish attribute holders, but
    occasionally show up as dicts (zeep-version dependent). Try both.
    """
    if obj is None:
        return default
    if hasattr(obj, "__getitem__") and not hasattr(obj, "__getattr__"):
        return obj.get(name, default)
    return getattr(obj, name, default)


class CUCMSourceAdapter(Adapter):
    """DiffSync adapter that loads CUCM state via AXL."""

    phone_system = PhoneSystemModel
    partition = PartitionModel
    calling_search_space = CallingSearchSpaceModel
    directory_number = DirectoryNumberModel
    phone = PhoneModel
    line = LineModel
    trunk = TrunkModel
    route_pattern = RoutePatternModel
    analog_gateway = AnalogGatewayModel

    top_level = (
        "phone_system",
        "partition",
        "calling_search_space",
        "directory_number",
        "phone",
        "line",
        "trunk",
        "route_pattern",
        "analog_gateway",
    )

    type = "cisco-ucm"

    def __init__(self, *args, client, phone_system_record, job=None, **kwargs):
        """Take a configured AXLClient and the PhoneSystem record it belongs to.

        `phone_system_record` is the Nautobot PhoneSystem ORM instance —
        we need its name + version for the synthetic phone_system DiffSync
        record we emit (CUCM doesn't have a "phone system" object; the
        cluster IS the system).
        """
        super().__init__(*args, **kwargs)
        self.client = client
        self.phone_system_record = phone_system_record
        self.job = job

    def load(self) -> None:
        """Walk AXL listX operations and populate DiffSync models."""
        # Synthetic top-level record for the cluster itself.
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
        self._load_phones_and_lines(ps.name)
        self._load_trunks(ps.name)
        self._load_route_patterns(ps.name)
        self._load_gateways(ps.name)

    # -- Per-collection loaders ----------------------------------------------

    def _load_partitions(self, ps_name: str) -> None:
        for row in self.client.list_route_partitions():
            self.add(self.partition(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                description=_get(row, "description", "") or "",
            ))

    def _load_calling_search_spaces(self, ps_name: str) -> None:
        for row in self.client.list_css():
            self.add(self.calling_search_space(
                name=_get(row, "name", ""),
                phone_system__name=ps_name,
                description=_get(row, "description", "") or "",
            ))

    def _load_directory_numbers(self, ps_name: str) -> None:
        for row in self.client.list_lines():
            partition_ref = _get(row, "routePartitionName")
            partition_name = _get(partition_ref, "_value_1", "") if partition_ref is not None else ""
            self.add(self.directory_number(
                extension=_get(row, "pattern", ""),
                partition__name=partition_name,
                partition__phone_system__name=ps_name,
                alerting_name=_get(row, "alertingName", "") or "",
                voicemail_profile=_get(_get(row, "voiceMailProfileName"), "_value_1", "") or "",
                vendor_extras=_extract_extras(row, exclude={"pattern", "routePartitionName", "alertingName"}),
            ))

    def _load_phones_and_lines(self, ps_name: str) -> None:
        for phone_row in self.client.list_phones():
            device_name = _get(phone_row, "name", "")
            mac = (_get(phone_row, "name", "") or "").removeprefix("SEP").lower()
            mac_formatted = ":".join(mac[i:i + 2] for i in range(0, len(mac), 2)) if len(mac) == 12 else mac

            self.add(self.phone(
                mac_address=mac_formatted,
                phone_system__name=ps_name,
                device_name=device_name,
                model=_get(phone_row, "model", "") or "",
                registration_status=_get(phone_row, "currentRegistrationStatus", "unknown") or "unknown",
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
                    label=_get(line, "label", "") or "",
                    ring_setting=_get(line, "ringSetting", "") or "",
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
        for row in self.client.list_route_patterns():
            partition_ref = _get(row, "routePartitionName")
            partition_name = _get(partition_ref, "_value_1", "") if partition_ref else ""
            self.add(self.route_pattern(
                pattern=_get(row, "pattern", ""),
                partition__name=partition_name,
                partition__phone_system__name=ps_name,
                urgent=bool(_get(row, "patternUrgency", False)),
                discard_digits=_get(row, "discardDigits", "") or "",
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
