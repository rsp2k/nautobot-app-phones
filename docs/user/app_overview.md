# App Overview

## What gets synced

The app pulls data from a CCM cluster's **AXL SOAP API** (configuration) and
**RisPort70 real-time service** (live device state) and writes it into
~20 Django models grouped by domain:

### Dial Plan
- `Partition` — namespace for routing decisions
- `CallingSearchSpace` — ordered list of partitions a caller can reach
- `CSSPartitionMembership` — through-table preserving CSS partition order

### Numbers
- `DirectoryNumber` — a CCM "Line" object (DN + partition)
- `DIDBlock` — E.164 ranges (start/end same-prefix same-length)
- `DID` — individual DIDs materialized on assignment
- `DIDAssignment` — generic FK linking a DID to a DN/Trunk/voicemail target
- `SipCircuitProfile` — SIP-specific extension on Nautobot's built-in `circuits.Circuit` (concurrent sessions, pilot DID, OLI/CLID policy, cut-sheet provenance). The underlying carrier is Nautobot's `circuits.Provider`.

### Endpoints
- `Phone` — every CCM phone-class device. Eight `device_kind` values:
  SEP (physical IP), CSF (Jabber Desktop), TCT (Jabber iOS), BOT (Jabber Android),
  CSK (CSF variant), ATA (analog terminal adapter), CCX (Contact Center CTI),
  CER (Emergency Responder CTI), CTI (custom virtual endpoint)
- `Line` — a DN appearance on a phone button (max calls, busy trigger, MWI policy)
- `SpeedDial` — speed-dial button on a phone
- `BusyLampField` — BLF watch button (presence-aware speed dial)
- `PhoneServiceUrl` — XML service URL button (Extension Mobility, custom apps)

### Routing
- `Trunk` — SIP/PRI/H.323/MGCP trunks
- `RoutePattern` — outbound dial-plan match (XOR target_trunk/target_route_list/target_dn)
- `RouteList` — priority list of route groups
- `RouteGroup` — load-balanced trunk group
- `TranslationPattern` — digit-rewrite pattern (pre-routing)

### Hunt
- `HuntPilot` — pattern that fronts a hunt list (e.g. `1204` → "ring the HIM team")
- `HuntList` — ordered set of LineGroups, evaluated when a HuntPilot matches
- `LineGroup` — ordered set of DNs with a distribution algorithm (Top Down,
  Circular, Broadcast, Longest Idle Time)

### Features (vendor-agnostic shared config)
- `DeviceProfile` — named bundle of device-config defaults applied to phones
  (maps to CCM DevicePool / FreePBX device template). Cisco-specific bundled
  refs (Region, Location, CMG, etc.) live in `vendor_extras` since other
  vendors don't have those concepts.
- `VoicemailProfile` — voicemail box config; referenced by FK from
  DirectoryNumber.
- `CallPickupGroup` — extension that grabs a ringing peer (e.g. `*8`).
  Member DNs join through `CallPickupGroupMember`.

### Analog
- `AnalogGateway` — Cisco voice gateway (VG450, VG350, etc.)
- `AnalogPort` — FXS/FXO port on a gateway, optionally bound to a DN

### System
- `PhoneSystem` — the CCM cluster itself (vendor, hostname, secrets)

## How sync works

The app uses the [Nautobot SSoT](https://github.com/nautobot/nautobot-app-ssot)
framework. Each sync run:

1. **Source-side load** — talks to the CCM cluster's AXL endpoint, walks
   `listX` calls (`listPhone`, `listRoutePartition`, `listSipTrunk`, etc.),
   constructs DiffSync model objects.
2. **Target-side load** — reads the current state from the Nautobot ORM.
3. **Diff** — DiffSync compares the two by natural keys, produces a list
   of creates/updates/deletes.
4. **Apply** — runs the changes through Nautobot's standard ORM machinery
   (custom field validation, change-log entries, signals fire).

By default, runs are **dry-run** (set the `dryrun` toggle to `false` to
actually apply changes).

## Live status (RisPort70)

When `enrich_phone_ip=true`, the sync calls RisPort70's `selectCmDevice`
operation and populates per-phone:

- **`active_load`** — running firmware (SEP) or Webex/Jabber build (CSF/TCT/BOT).
  Examples: `Webex_for_Windows-46.4.0.34752`, `sip78xx.14-3-1-0001-60`.
- **`inactive_load`** — rollback target (relevant for IP phones).
- **`live_login_user`** — who's signed in right now.
- **`status_reason`** — Cisco's reason code, mapped to human labels
  (`6 — Authentication failed`, etc.).
- **`live_status_polled_at`** — capture timestamp.

Live-status fields go stale fast — pair the polled-at timestamp with your
sync schedule when interpreting the data.

## DCIM linkage

The sync optionally creates Nautobot `dcim.Device` records for each Phone
and matches existing Devices for AnalogGateways. This unlocks:

- **Cabling** — connect phone interfaces → switch ports → patch panels
- **IP addresses** — phone IPs become first-class IPAM records
- **Racks/locations** — phones inherit physical placement from their Device

For analog gateways, FXS/FXO port Interfaces get auto-materialized on the
linked Device using Cisco IOS voice-port naming (`voice-port 1/0/0`,
`voice-port 3/0/55`) so the gateway's running-config and Nautobot DCIM
share the same identifiers.

Two CustomFields tag each port as FXS/FXO (function) and RJ-11/RJ-21
(connector). See [Sync Reference](sync_reference.md) for details.
