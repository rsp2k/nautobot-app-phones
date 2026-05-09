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
        self._load_extensions(ps.name)

        # Stages 5+:
        # self._load_voicemail_profiles(ps.name)
        # self._load_trunks(ps.name)
        # self._load_outbound_routes(ps.name)
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
