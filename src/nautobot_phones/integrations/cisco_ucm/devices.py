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

import ipaddress as _ipaddress

from django.contrib.contenttypes.models import ContentType
from django.utils.text import slugify

from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Manufacturer
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

from nautobot_phones.models import AnalogGateway, AnalogPort, Phone


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

    skipped_softphone = 0
    # Only physical endpoints get DCIM Devices. Jabber softphones (CSF/TCT/
    # BOT/CSK) are software endpoints — they don't have cabling, ports, or
    # rack positions. Trying to model them in DCIM would force-fit unrelated
    # concepts. They live as Phone records only.
    HARDWARE_KINDS = {"sep", "ata"}

    for phone in Phone.objects.select_related("device", "phone_system__location"):
        if phone.device_id is not None:
            skipped_already_linked += 1
            continue
        if phone.device_kind not in HARDWARE_KINDS:
            skipped_softphone += 1
            continue

        # Phone.location was removed (it was a dcim.Location FK that got
        # confused with CCM's "Location" CAC concept). Physical placement
        # now flows through PhoneSystem.location → Device.location → and
        # then back through Phone.location's @property accessor.
        location = phone.phone_system.location or default_location
        if location is None:
            skipped_no_location += 1
            continue

        try:
            # `axl_model` is stashed in vendor_extras by the adapter at sync
            # time — Phone.model itself was removed (Nautobot DCIM is the
            # source of truth for hardware identity, and DeviceType.model
            # is what we'll read back through the @property).
            axl_model = (phone.vendor_extras or {}).get("axl_model", "") or "Unknown Cisco Phone"
            device_type = _ensure_device_type(cisco, axl_model)
            device = Device.objects.create(
                name=phone.device_name,
                device_type=device_type,
                role=role,
                status=active,
                location=location,
                serial=str(phone.mac_address).upper() if phone.mac_address else "",
            )
            voice_iface, network_iface = _create_phone_interfaces(device, axl_model)
            # Assign Phone.last_registered_ip to Voice (preferred) or Network
            # interface, and set as the Device's primary IPv4 so it shows up
            # in the standard Device list view and SNMP-discovery flows.
            if phone.last_registered_ip:
                ip_iface = voice_iface or network_iface
                ip_addr = _ensure_ip_address(phone.last_registered_ip)
                IPAddressToInterface.objects.get_or_create(
                    ip_address=ip_addr,
                    interface=ip_iface,
                )
                if ":" in phone.last_registered_ip:
                    device.primary_ip6 = ip_addr
                else:
                    device.primary_ip4 = ip_addr
                device.save()
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
        "skipped_softphone": skipped_softphone,
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


def _create_phone_interfaces(device: Device, phone_model: str) -> tuple[Interface | None, Interface]:
    """Create Network / PC / Voice interfaces on the new Device.

    Returns (voice_iface, network_iface) — voice_iface is None for
    single-port models. Caller uses one of them as the IP-binding target.

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

    voice = None
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
        voice = Interface.objects.create(
            device=device,
            name="Voice",
            type=InterfaceTypeChoices.TYPE_VIRTUAL,
            parent_interface=network,
            status=active_iface,
            description="Voice VLAN sub-interface (no connector). Assign voice VLAN below.",
        )
    return voice, network


def _ensure_ip_address(ip_str: str) -> IPAddress:
    """Find or create an IPAddress for `ip_str`, hosting it under a /32 (or
    /128) Prefix in the Global namespace.

    Nautobot 3.x requires every IPAddress to have a parent Prefix in some
    Namespace. We use the default 'Global' namespace and create a single-
    host Prefix per IP — operators can later move the IP under a wider
    prefix if they prefer (Nautobot supports re-parenting).
    """
    parsed = _ipaddress.ip_address(ip_str)
    is_v6 = parsed.version == 6
    mask = 128 if is_v6 else 32
    ns = Namespace.objects.get(name="Global")
    prefix_str = f"{ip_str}/{mask}"
    active_pfx = Status.objects.get_for_model(Prefix).get(name="Active")
    active_ip = Status.objects.get_for_model(IPAddress).get(name="Active")
    prefix, _ = Prefix.objects.get_or_create(
        prefix=prefix_str,
        namespace=ns,
        defaults={"status": active_pfx, "type": "container"},
    )
    ip, _ = IPAddress.objects.get_or_create(
        host=ip_str,
        parent=prefix,
        defaults={"status": active_ip, "mask_length": mask},
    )
    return ip


# --------------------------------------------------------------------------
# AnalogGateway → DCIM Device matching
# --------------------------------------------------------------------------
#
# Unlike Phones (where CCM device-name encodes the chassis MAC), CCM gateway
# names are operator-chosen and rarely match the network hostname. For
# example, CCM might call a gateway `SITE-GW-001` while DCIM has it as
# `RACK-R00-ANALOG-GW`. We can't rely on a single matching strategy —
# try several in order, log unmatched gateways for operator action.

def enrich_analog_gateway_devices(*, logger=None) -> dict:
    """Match each AnalogGateway to an existing dcim.Device.

    Multi-strategy linker (does NOT create Devices — gateways come from
    network discovery, not CCM. Auto-creating risks duplicates against
    DCIM's authoritative inventory):

      1. **Exact name match**: Device.name == AnalogGateway.name. Hits
         when CCM device-name and network hostname happen to align.

      2. **MAC-base hint**: extract the 4-byte chassis MAC base from the
         CCM device-name (last 10 chars minus '01' suffix) and search
         Device.serial / Device.name / Device.comments for it. Hits in
         shops that name devices by MAC.

      3. **Unique DeviceType in PhoneSystem location**: if the gateway's
         model (e.g. VG450) matches exactly one Device of that DeviceType
         in the PhoneSystem's Location, link it. Catches single-gateway
         deployments where exactly one chassis of the model exists at
         the cluster's site.

    Operators can always override by setting AnalogGateway.device manually
    in the UI; once linked, this pass leaves it alone.
    """
    log = (logger.info if logger else print)
    matched_exact = matched_mac_base = matched_unique_dt = 0
    skipped_already_linked = unmatched = 0

    for gw in AnalogGateway.objects.select_related("device", "phone_system__location"):
        if gw.device_id is not None:
            skipped_already_linked += 1
            continue

        device = None
        match_strategy = None

        # Strategy 1: exact name match
        device = Device.objects.filter(name=gw.name).first()
        if device:
            match_strategy = "exact-name"
            matched_exact += 1

        # Strategy 2: MAC-base hint in serial/name/comments
        if device is None:
            mac_base = _extract_chassis_mac_base(gw.name)
            if mac_base:
                from django.db.models import Q
                device = Device.objects.filter(
                    Q(serial__icontains=mac_base)
                    | Q(name__icontains=mac_base)
                    | Q(comments__icontains=mac_base)
                ).first()
                if device:
                    match_strategy = f"mac-base[{mac_base}]"
                    matched_mac_base += 1

        # Strategy 3: unique DeviceType match.
        #
        # First try within the PhoneSystem's Location (most precise — handles
        # multi-site clusters where each site has its own gateway). If that
        # returns nothing (common when CCM-side and DCIM-side use different
        # location-naming conventions), fall back to cluster-wide uniqueness.
        # Only auto-link if there's exactly ONE candidate; ambiguity stays
        # unmatched so the operator picks.
        if device is None and gw.model:
            cluster_location = gw.phone_system.location if gw.phone_system_id else None
            base_qs = Device.objects.filter(device_type__model__iexact=gw.model)
            if cluster_location:
                scoped = base_qs.filter(location=cluster_location)
                if scoped.count() == 1:
                    device = scoped.first()
                    match_strategy = f"unique-{gw.model}-in-{cluster_location.name}"
                    matched_unique_dt += 1
            if device is None and base_qs.count() == 1:
                device = base_qs.first()
                match_strategy = f"unique-{gw.model}-cluster-wide"
                matched_unique_dt += 1

        if device is None:
            unmatched += 1
            log(f"  AnalogGateway '{gw.name}' (model={gw.model}) — no Device match. "
                f"Set the link manually in the UI.")
            continue

        gw.device = device
        gw.save()
        log(f"  Linked AnalogGateway '{gw.name}' → Device '{device.name}' "
            f"({device.serial or 'no-serial'}) via {match_strategy}")

    return {
        "matched_exact": matched_exact,
        "matched_mac_base": matched_mac_base,
        "matched_unique_dt": matched_unique_dt,
        "skipped_already_linked": skipped_already_linked,
        "unmatched": unmatched,
    }


def _extract_chassis_mac_base(ccm_name: str) -> str:
    """Extract the chassis MAC base from a CCM gateway name.

    Common CCM gateway-naming convention: ``<SITE>GW<base-mac><01>``
    where ``base-mac`` is the 4-byte chassis MAC (8 hex chars) and ``01``
    is a constant unit-marker suffix. For a name like ``HQGW4ABC0DEF01``
    this yields ``4ABC0DEF`` as the MAC base.

    Returns empty string when the name doesn't match the expected shape —
    callers fall through to other matching strategies.
    """
    if len(ccm_name) < 10:
        return ""
    suffix10 = ccm_name[-10:].upper()
    if not suffix10.endswith("01"):
        return ""
    base = suffix10[:8]
    # Must be all-hex (or it's not a MAC base)
    try:
        int(base, 16)
        return base
    except ValueError:
        return ""


def _decode_voice_port_name(port_index: int) -> str:
    """Decode CCM AN4 port encoding into Cisco IOS voice-port slot/subslot/port.

    Empirical decoding (verified against multiple VG450 chassis
    running-configs and audit-published port mapping tables):

        bits 9-11  → slot
        bit 8      → sub-slot
        bits 0-7   → port number (1-based; IOS displays as port-1)

    Examples (audit-verified):
        0x20A (522)  → voice-port 1/0/9
        0x638 (1592) → voice-port 3/0/55
        0x201 (513)  → voice-port 1/0/0
    """
    slot = (port_index >> 9) & 0x07
    sub_slot = (port_index >> 8) & 0x01
    port_1based = port_index & 0xFF
    port = port_1based - 1
    if port < 0:
        # Encoding boundary case — fall back to a stable raw-hex name
        # so the Interface still gets created with a unique, decodable label.
        return f"FXS-0x{port_index:X}"
    return f"voice-port {slot}/{sub_slot}/{port}"


def _voice_port_metadata(subunit_product: str) -> tuple[str, str]:
    """Map a Cisco voice-module product string to (function, connector).

    Function detection by name (FXS/FXO substrings). Connector detection
    by density-implied form-factor:
      - SM-X / SM-* with high port count → RJ-21 (50-pin Amphenol)
      - NIM-* with low port count        → RJ-11 (individual jacks)

    Defaults to ``fxs / rj-21`` (the SM-X-72FXS-SCCP case in our test fleet)
    when the subunit product is unknown — operators can override per-port
    via the Interface custom-field UI.
    """
    p = (subunit_product or "").upper()
    if "FXO" in p and "FXS" not in p:
        function = "fxo"
    elif "FXS" in p and "FXO" in p:
        # Mixed module — default to fxs (most common port type on these
        # cards); per-port override is the operator's responsibility.
        function = "fxs"
    else:
        function = "fxs"

    high_density = any(d in p for d in ("24FXS", "48FXS", "72FXS", "24FXO", "48FXO"))
    if high_density or "SM-X" in p or "SM-" in p:
        connector = "rj-21"
    elif "NIM" in p:
        connector = "rj-11"
    else:
        connector = "rj-21"
    return function, connector


def enrich_analog_gateway_interfaces(*, logger=None) -> dict:
    """For each linked AnalogGateway, materialize FXS Interfaces on the Device.

    Walks the gateway's AnalogPort records and creates one Interface per
    port on the linked dcim.Device. Each Interface is named in Cisco IOS
    voice-port convention (`voice-port 1/0/0` etc.) so operators jumping
    between Nautobot DCIM and the gateway's running-config see the same
    identifiers in both places. Description carries the bound DN when
    one exists, making "what extension does this port serve?" answerable
    from the DCIM view.

    Idempotent: re-running adds nothing (get_or_create on name).
    Skips gateways that aren't linked to a Device yet.
    """
    log = (logger.info if logger else print)
    created = updated = skipped_no_device = errored = 0
    active_iface_status = Status.objects.get_for_model(Interface).get(name="Active")

    for gw in AnalogGateway.objects.select_related("device"):
        if gw.device_id is None:
            skipped_no_device += 1
            continue
        # Build subunit-product lookup keyed by (unit_index, subunit_index)
        # — captured during gateway sync into vendor_extras.module_units.
        # Each port's bit-decode tells us which (unit, subunit) it lives on,
        # so we can populate function + connector custom fields per port.
        subunit_products: dict[tuple[int, int], str] = {}
        for unit_info in (gw.vendor_extras or {}).get("module_units", []) or []:
            ui = unit_info.get("unit_index")
            si = unit_info.get("subunit_index")
            sp = unit_info.get("subunit_product") or ""
            if ui is not None and si is not None:
                subunit_products[(int(ui), int(si))] = sp

        for port in gw.ports.select_related("directory_number__partition"):
            iface_name = _decode_voice_port_name(port.port_index)
            # Decode slot/sub_slot for module lookup. Same bit layout as
            # the IOS-name decoder.
            slot = (port.port_index >> 9) & 0x07
            sub_slot = (port.port_index >> 8) & 0x01
            subunit_product = subunit_products.get((slot, sub_slot), "")
            voice_fn, phys_conn = _voice_port_metadata(subunit_product)

            description_bits = [f"{voice_fn.upper()} port (CCM index 0x{port.port_index:X} = {port.port_index})"]
            if subunit_product:
                description_bits.append(f"on {subunit_product}")
            if port.directory_number_id:
                dn = port.directory_number
                description_bits.append(f"DN {dn.partition.name}/{dn.extension}")
            description = " — ".join(description_bits)

            try:
                iface, was_created = Interface.objects.get_or_create(
                    device=gw.device,
                    name=iface_name,
                    defaults={
                        "type": InterfaceTypeChoices.TYPE_OTHER,  # FXS/FXO isn't a core type
                        "status": active_iface_status,
                        "description": description,
                    },
                )
                # Populate custom fields. ``_custom_field_data`` is the
                # canonical write surface for CustomField values on
                # Nautobot models — round-trips through validation.
                desired_cf = {"voice_function": voice_fn, "physical_connector": phys_conn}
                cf_changed = any(
                    iface._custom_field_data.get(k) != v for k, v in desired_cf.items()
                )
                desc_changed = iface.description != description
                if was_created:
                    iface._custom_field_data.update(desired_cf)
                    iface.save()
                    created += 1
                elif cf_changed or desc_changed:
                    iface._custom_field_data.update(desired_cf)
                    iface.description = description
                    iface.save()
                    updated += 1
            except Exception as exc:  # noqa: BLE001
                log(f"  Failed to create Interface for {gw.name} port {port.port_index}: {exc}")
                errored += 1

    return {
        "created": created,
        "updated": updated,
        "skipped_no_device": skipped_no_device,
        "errored": errored,
    }
