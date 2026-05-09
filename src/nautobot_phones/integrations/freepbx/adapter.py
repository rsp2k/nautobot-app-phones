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
        # self._load_extensions(ps.name)

        # Stages 5+:
        # self._load_voicemail_profiles(ps.name)
        # self._load_trunks(ps.name)
        # self._load_outbound_routes(ps.name)
        # self._load_ring_groups(ps.name)
        # self._load_pickup_groups(ps.name)

    # -------------------------------------------- per-resource loaders

    def _load_extensions(self, ps_name: str) -> None:
        """Fetch extensions, emit one DirectoryNumber + Phone per record.

        STUB — will be implemented in stage 4 once we have a seeded
        FreePBX with API credentials and can confirm the actual GraphQL
        response shape.
        """
        raise NotImplementedError("Stage 4 — see SEED_PLAN.md")
