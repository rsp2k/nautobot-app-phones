# Sync Reference

This page documents both vendor adapters — what data each one reads,
how it maps to the unified model graph, and which job toggles control
the load.

| Vendor | Job class | Transport | Auth |
|--------|-----------|-----------|------|
| Cisco UCM (CCM) 15.x | `CUCMDataSource` | AXL SOAP + RisPort70 | HTTP Basic (read-only AXL app user) |
| FreePBX 17 | `FreePBXDataSource` | GraphQL + DB-direct (MariaDB) | OAuth2 client_credentials + DB-SELECT-only role |

Both adapters are read-only — Nautobot is the mirror, the vendor is the
source of truth.

## Job toggles

| Toggle | Default | What it does |
|--------|---------|--------------|
| `dryrun` | `True` | Generate diff artifact without applying changes |
| `verify_tls` | `True` | Validate CCM's HTTPS certificate. Off only for dev clusters with self-signed certs |
| `enrich_phone_ip` | `False` | Call RisPort70 (single bulk call) — populates `last_registered_ip`, `registration_status`, `active_load`, `inactive_load`, `live_login_user`, `status_reason`, `live_status_polled_at`. Cheap (~seconds). Recommended on. |
| `enrich_phone_lines` | `False` | Per-phone `getPhone` enrichment — populates Lines, SpeedDials, BusyLampFields, PhoneServiceUrls + per-line fields (`max_num_calls`, `busy_trigger`, `mwl_policy`, etc.). Slow (~200-400ms × N phones). |
| `enrich_phone_devices` | `False` | Auto-create dcim.Device records for each Phone + match AnalogGateways → existing Devices + materialize FXS Interfaces |
| `default_phone_location` | (unset) | Fallback `dcim.Location` for Phones whose PhoneSystem has no Location set |

## What's queryable

### Phone fields

The schema separates **general-telephony columns** (queryable, filterable,
common across vendors) from **vendor-specific extras** that flow through
the `vendor_extras` JSONField. Phone-side columns are intentionally
trimmed to fields that map cleanly across CCM, FreePBX, and future
adapters.

| Column | Source (CCM) | Source (FreePBX) | Notes |
|--------|--------------|------------------|-------|
| `device_name` | AXL `name` | `<technology>/<extension>` or device MAC | Canonical per-vendor identifier |
| `device_kind` | derived from name prefix | derived | `sep`/`csf`/`tct`/`bot`/`csk`/`ata`/`ccx`/`cer`/`cti`/`other` |
| `mac_address` | derived (SEP/ATA) or null | from `coreDevice` | Softphones have none |
| `description` | AXL `description` | extension display name | |
| `owner_user_id` | AXL `ownerUserName` | user FK | Assigned user |
| `dnd_status` / `dnd_option` | AXL `dndStatus` / `dndOption` | (varies) | Do-not-disturb state |
| `device_profile` (FK) | AXL `devicePoolName` → DeviceProfile | (n/a yet) | Vendor-agnostic profile bundle |
| `media_zone` | AXL `locationName` | site/tenant string | Bandwidth-admission boundary (renamed from `ccm_location`) |
| `user_locale`, `network_locale` | AXL locale fields | (n/a) | Regional config |
| `active_load` | RIS `ActiveLoadID` | (n/a) | Running firmware/Webex build |
| `inactive_load` | RIS `InactiveLoadID` | (n/a) | Rollback target |
| `live_login_user` | RIS `LoginUserId` | (n/a) | Signed-in user |
| `status_reason` | RIS `StatusReason` | (n/a) | Cisco reason code (UI maps to label) |
| `live_status_polled_at` | (sync timestamp) | (n/a) | When the RIS data was captured |
| `registration_status` | RIS / GraphQL | endpoint status | |

CCM-specific provisioning details — `built_in_bridge`, `privacy`,
`device_mobility_mode`, `device_security_profile`, `sip_profile`,
`rerouting_css`, `subscribe_css`, `mtp_required`, `packet_capture_mode`,
`common_phone_profile`, `common_device_configuration`,
`phone_button_template`, `softkey_template`, `mobility_user_id`,
`aar_neighborhood`, `always_use_prime_line*`, `network_location`,
etc. — flow into `vendor_extras` as named keys. They remain
fully readable but aren't filterable as ORM columns.

### Line fields (per-DN-appearance)

| Column | Notes |
|--------|-------|
| `phone`, `directory_number`, `button_index` | identifiers |
| `label`, `display`, `ring_setting` | Display + ring behavior |
| `max_num_calls`, `busy_trigger` | Call-capacity bounds (Default 4 / 2 on CCM) |
| `missed_call_logging` | bool |

CCM-specific per-line config (`mwl_policy`, `audible_mwi`,
`partition_usage`, `consecutive_ring_setting`, `ring_setting_idle_pickup_alert`,
`ring_setting_active_pickup_alert`, `recording_flag`) flows into
`Line.vendor_extras` rather than dedicated columns.

### Vendor-agnostic Phone/Line schema

The Phone and Line models keep only general-telephony fields as columns;
CCM-specific provisioning details live in `vendor_extras` so the schema
stays vendor-portable. New adapters populate the columns directly and
shovel anything vendor-specific into `vendor_extras`.

`Phone.media_zone` is the vendor-agnostic name for the media/bandwidth
admission boundary — Cisco calls it Location, Avaya calls it Network
Region, FreePBX deployments may call it site or tenant. Stored as a
free-form CharField so any vendor can populate it.

### Hunt subsystem

Three first-class records and two through-tables, in the order CCM
evaluates them at call time:

| Model | Source AXL ops | Notes |
|-------|---------------|-------|
| `LineGroup` | `listLineGroup` + `getLineGroup` | listX returns scalars only; getX returns the ordered DN membership |
| `LineGroupMember` | (member rows from `getLineGroup`) | `line_selection_order` controls hunt order within the group |
| `HuntList` | `listHuntList` + `getHuntList` | listX returns scalars; getX returns the ordered LineGroup membership |
| `HuntListMember` | (member rows from `getHuntList`) | `selection_order` is the priority across LineGroups in the same HuntList |
| `HuntPilot` | `listHuntPilot` | Single-pass; AXL exposes `huntListName`, `forwardHuntNoAnswer`, `forwardHuntBusy` directly |

`distribution_algorithm` on `LineGroup` is one of `Top Down`, `Circular`,
`Broadcast`, `Longest Idle Time` — CCM's stored values, used as-is. The
three `hunt_algorithm_*` fields on LineGroup are full natural-language
phrases as CCM stores them (e.g. `Try next member; then, try next group
in Hunt List`); these can be 50 chars long, so the columns are sized at
100.

### Vendor-agnostic feature config

Three vendor-agnostic shared-config models populated from CCM listX/getX
operations. Designed so a FreePBX (or other vendor) adapter can populate
them without schema migrations.

| Model | Source AXL ops | Notes |
|-------|---------------|-------|
| `DeviceProfile` | `listDevicePool` + `getDevicePool` | Vendor-agnostic name for "named device-config bundle". CCM-specific refs (CMG, Region, Location, DateTimeGroup, SRST, MRGL) go in `vendor_extras` rather than first-class tables — those concepts are CCM-only. |
| `VoicemailProfile` | `listVoiceMailProfile` + `getVoiceMailProfile` | Pilot DN, mailbox mask, default flag. `DirectoryNumber.voicemail_profile` is a FK to this. |
| `CallPickupGroup` | `listCallPickupGroup` + `getCallPickupGroup` | Pattern dialed to invoke pickup. Note: AXL's `listCallPickupGroup` searches by `pattern` not `name`. |
| `CallPickupGroupMember` | (`listLine` callPickupGroupName) | DN→Group association. CCM stores it on the DN side via `callPickupGroupName`, not in the group's `members` (which is the chained-fall-through *between groups*). Adapter walks listLine to collect them. |

`Phone.device_profile` and `DirectoryNumber.voicemail_profile` are
nullable FKs — they resolve to None if the source CCM record has no
profile assigned.

## FreePBX 17 adapter

The FreePBX adapter (`FreePBXDataSource`) uses three data sources
because the FreePBX 17 `api` module (currently 17.0.6) doesn't expose
every resource through GraphQL. The adapter falls back to read-only
SQL against the underlying MariaDB for trunks and outbound routes,
and uses an HTTP fetch for inbound routes when those aren't in the
configured GraphQL schema yet.

| Resource | Source | Notes |
|----------|--------|-------|
| Extensions → `DirectoryNumber` + `Phone` | GraphQL `fetchAllExtensions` | Connection wrapper — adapter flattens `user{}` + `coreDevice{}` |
| Trunks → `Trunk` | DB `trunks` table | Asterisk's `pjsip` table backs SIP trunks; chan_sip is deprecated in Asterisk 21 and skipped |
| Outbound routes → `RouteList` + synthetic `RouteGroup` + `RouteGroupMember` + `RoutePattern` | DB `outbound_routes` / `outbound_routes_patterns` | One-trunk-per-group simplification (FreePBX has no separate group concept) |
| Inbound routes → `RoutePattern` (with `target_dn`) | DB `incoming` table | Only `Extensions:<ext>` destinations populate `target_dn`; queue/IVR/ring-group/voicemail destinations are skipped |
| Voicemail profiles → `VoicemailProfile` | GraphQL `fetchVoiceMail` | Pilot DN + mailbox mask |
| Ring groups → `HuntPilot` + `HuntList` + `LineGroup` + members | DB `ringgroups` + `ringgroups_members` | FreePBX has one ringgroup; we synthesize a HuntList + LineGroup per ringgroup so the unified hunt subsystem stays consistent with CCM |
| Pickup groups | (defensive stub) | FreePBX 17.0.6 doesn't expose these via the API; the loader is a no-op until upstream catches up |

The adapter participates in the same vendor-agnostic feature-config
layer as CCM: `VoicemailProfile` and (eventually) `DeviceProfile` /
`CallPickupGroup` records are emitted into the same table that CCM
populates. Operators see one unified list across vendors.

**Strategy mapping for ring-groups → hunt** — FreePBX ring strategy
strings map to CCM's `distribution_algorithm` choices:

| FreePBX strategy | → unified `distribution_algorithm` |
|------------------|------------------------------------|
| `ringall`, `ringall_v2` | `Broadcast` |
| `hunt`, `firstavailable` | `Top Down` |
| `memoryhunt`, `memoryhunt_v2`, `rrmemory` | `Circular` |
| (anything else) | `Top Down` (fallback) |

## Through-tables (M2M with attributes)

Some relationships carry their own attributes (e.g. priority order) and
are modeled as explicit "through-table" rows rather than M2M shortcuts.

### `RouteListMember` — ordered RouteGroup membership inside a RouteList

| Column | Source (CCM) | Source (FreePBX) |
|--------|--------------|------------------|
| `route_list` (FK) | `getRouteList.name` | outbound route name |
| `route_group` (FK) | `getRouteList.members.member[*].routeGroupName._value_1` | synthesized trunk name |
| `priority` | `getRouteList.members.member[*].selectionOrder` | `outbound_routes_trunks.seq` |

Lower number = evaluated first. CCM clusters typically have one or two
groups per list; FreePBX always one (since each trunk becomes its own
synthesized group).

### `RouteGroupMember` — devices inside a RouteGroup (GFK target)

This table uses a `GenericForeignKey` because a Route Group's member
can be either a Trunk or an AnalogGateway (CCM) — different ORM models.

| Column | Source (CCM) | Source (FreePBX) |
|--------|--------------|------------------|
| `route_group` (FK) | `getRouteGroup.name` | synthesized trunk name |
| `target_type` (GFK) | derived from device class | always Trunk |
| `target` (GFK) | matched by device name against in-memory Trunk/AnalogGateway store | the underlying Trunk |
| `priority` | `getRouteGroup.members.member[*].deviceSelectionOrder` | always 1 |

CCM members that don't match any modeled Trunk or AnalogGateway
(typically Phones or CTI Route Points used as direct route-group
targets) are silently skipped.

### `DIDAssignment` — DID → routing target (operator-driven)

OneToOne from a DID record to whatever the operator pointed it at:
either a `DirectoryNumber` (the most common case — DID rings an
extension) or a `Trunk` (DID is owned by a downstream PBX reached
via that trunk).

| Column | Type | Notes |
|--------|------|-------|
| `did` (OneToOne) | FK → DID | identifier — natural key is `did.e164` |
| `target_kind` | derived from ContentType | `"directorynumber"` or `"trunk"` |
| `target_name` | string | For DN: the extension; for Trunk: the trunk name |
| `target_partition__name` | string | DN-only (Trunks have no partition) |
| `target_phone_system__name` | string | Scopes the target lookup |

**No source-adapter populates this.** DIDs come in via the
`ingest_sip_cut_sheet` management command (cut-sheet → DIDBlock +
DID), then operators wire assignments through the Nautobot UI. The
DiffSync model exists so external systems can query the assignment
state via REST / GraphQL.

## Sync ordering (top-level)

DiffSync's `top_level` tuple defines load order, which matters for
identifier resolution (children reference parents by natural key):

1. `phone_system` — root
2. Dial plan: `partition`, `calling_search_space`, `css_partition_membership`
3. Feature config: `device_profile`, `voicemail_profile` (FK targets for Phone/DN)
4. Numbers: `directory_number`
5. Endpoints: `phone`
6. Phone children: `line`, `speed_dial`, `busy_lamp_field`, `phone_service_url`
7. Routing: `trunk`, `route_list`, `route_group`, `route_list_member`, `route_pattern`, `translation_pattern`
8. Analog: `analog_gateway`, `analog_port`
9. GFK through-table: `route_group_member` — must follow Trunk + AnalogGateway so target lookup resolves
10. Hunt: `line_group`, `hunt_list`, `line_group_member`, `hunt_list_member`, `hunt_pilot`
11. Pickup: `call_pickup_group`, `call_pickup_group_member`
12. `did_assignment` — operator-driven only; sits last so its GFK target (DN or Trunk) is already loaded

Within the hunt subsystem, groups must load before their member rows
(member identifiers reference the group by name), and HuntList must
load before HuntPilot because the pilot's natural foreign key is the
hunt-list name.

When `enrich_phone_lines=False`, the four "phone child" models are excluded
from the diff so existing records aren't orphan-deleted by a sync that
isn't capable of populating them.
