"""Auto-create Nautobot Device records (+ DeviceType + Interfaces) for Phones.

Runs as a post-sync step in the SSoT Job, gated by `enrich_phone_devices`.
For each Phone record, materializes a Nautobot DCIM `Device` so cabling
and patch-panel relationships work through Nautobot's core models.

Interface topology mirrors real Cisco IP phone hardware:

  Network (1000base-t)  ←  cabled to switch / patch panel (carries data + voice)
       │
       └── Voice (virtual)  ←  parent_interface=Network; voice VLAN lives here
  PC      (1000base-t)  ←  cabled to user's PC (pass-through, data VLAN only)

ATAs, wireless phones (7925/8821), and conference phones (7937/8831/8832)
get only Network — they don't have a PC pass-through port. Voice port is
only created when the model has 2+ physical ports (i.e., when PC exists),
since one-port devices don't need the voice/data VLAN abstraction.
"""

from __future__ import annotations

from django.utils.text import slugify

from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer
from nautobot.extras.models import Role, Status
from django.contrib.contenttypes.models import ContentType

from nautobot_phones.models import Phone


# Models that have only ONE physical port (no PC pass-through, no voice VLAN
# concept). Anything not in this set defaults to the standard Network+PC+Voice
# trio — modern Cisco IP phones overwhelmingly have all three.
_SINGLE_PORT_MODELS = frozenset({
    # Analog Telephone Adaptors
    "Analog Phone",
    "ATA-186", "ATA-187", "ATA-188",
    "Cisco ATA-186", "Cisco ATA-187", "Cisco ATA-188",
    "Cisco ATA 191", "Cisco ATA 192",
    # Wireless phones — no wired PC pass-through
    "Cisco 7925", "Cisco 7925G", "Cisco 7925G-EX", "Cisco 7926", "Cisco 7926G",
    "Cisco 8821", "Cisco 8821-EX",
    # Conference room phones — no PC port (only network)
    "Cisco 7935", "Cisco 7936", "Cisco 7937", "Cisco 7937G",
    "Cisco 8831", "Cisco 8832",
})


def has_pc_port(phone_model: str) -> bool:
    """Whether this phone model has a PC pass-through port + voice VLAN."""
    if not phone_model:
        return True  # default for unknown models — most modern phones have it
    return phone_model not in _SINGLE_PORT_MODELS


def enrich_phone_devices(*, default_location=None, logger=None) -> dict:
    """Walk Phone records, create Nautobot Device + DeviceType + Interfaces.

    Idempotent — phones that already have a Device link are skipped, and
    DeviceType + Manufacturer + Role lookups are get_or_create.

    `default_location` is the fallback when neither the Phone nor its
    PhoneSystem has a Location set. Phones with no resolvable location
    are skipped (Nautobot Devices require Location).

    Returns a dict with counts of created/skipped/errored phones.
    """
    log = (logger.info if logger else print)
    cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
    role, _ = _ensure_voip_phone_role()
    active = Status.objects.get_for_model(Device).get(name="Active")

    created = 0
    skipped_no_location = 0
    skipped_already_linked = 0
    errored = 0

    for phone in Phone.objects.select_related("device", "location", "phone_system__location"):
        if phone.device_id is not None:
            skipped_already_linked += 1
            continue

        location = phone.location or phone.phone_system.location or default_location
        if location is None:
            skipped_no_location += 1
            continue

        try:
            device_type = _ensure_device_type(cisco, phone.model or "Unknown Cisco Phone")
            device = Device.objects.create(
                name=phone.device_name,
                device_type=device_type,
                role=role,
                status=active,
                location=location,
                serial=str(phone.mac_address).upper() if phone.mac_address else "",
            )
            _create_phone_interfaces(device, phone.model or "")
            phone.device = device
            phone.save()
            created += 1
        except Exception as exc:  # noqa: BLE001 — log and continue, don't abort the whole pass
            log(f"Failed to create Device for {phone.device_name}: {exc}")
            errored += 1

    return {
        "created": created,
        "skipped_no_location": skipped_no_location,
        "skipped_already_linked": skipped_already_linked,
        "errored": errored,
    }


def _ensure_voip_phone_role() -> tuple[Role, bool]:
    """Find or create the VoIP Phone Role, ensuring Device is in its content_types."""
    role, created = Role.objects.get_or_create(name="VoIP Phone")
    device_ct = ContentType.objects.get_for_model(Device)
    if device_ct not in role.content_types.all():
        role.content_types.add(device_ct)
    return role, created


def _ensure_device_type(manufacturer: Manufacturer, model: str) -> DeviceType:
    """Find or create a DeviceType under the given manufacturer.

    Nautobot's DeviceType uniqueness is (manufacturer, model). If a type with
    this name already exists under another manufacturer, we'd hit IntegrityError
    — but Cisco phones under "Cisco" manufacturer is unambiguous in our use case.
    """
    dt, _ = DeviceType.objects.get_or_create(
        manufacturer=manufacturer,
        model=model,
        defaults={"u_height": 0, "is_full_depth": False},  # phones aren't rack-mounted
    )
    return dt


def _create_phone_interfaces(device: Device, phone_model: str) -> None:
    """Create Network / PC / Voice interfaces on the new Device.

    Network is always created. PC + Voice only when the model has a
    pass-through port (most modern Cisco IP phones — see _SINGLE_PORT_MODELS
    for exceptions).
    """
    active_iface = Status.objects.get_for_model(Interface).get(name="Active")

    network = Interface.objects.create(
        device=device,
        name="Network",
        type=InterfaceTypeChoices.TYPE_1GE_FIXED,
        status=active_iface,
        description="Upstream port — cabled to switch/patch panel. Carries data + voice VLANs.",
    )

    if has_pc_port(phone_model):
        Interface.objects.create(
            device=device,
            name="PC",
            type=InterfaceTypeChoices.TYPE_1GE_FIXED,
            status=active_iface,
            description="Pass-through port — cabled to user's PC. Data VLAN only.",
        )
        # Voice is virtual (hard-wired internally, no connector). Parented to
        # Network so cable traces show the voice traffic flowing through the
        # physical port. Operator assigns the actual voice VLAN.
        Interface.objects.create(
            device=device,
            name="Voice",
            type=InterfaceTypeChoices.TYPE_VIRTUAL,
            parent_interface=network,
            status=active_iface,
            description="Voice VLAN sub-interface (no connector). Assign voice VLAN below.",
        )
