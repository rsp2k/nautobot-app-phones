# Sync Reference

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

| Field | Source | Notes |
|-------|--------|-------|
| `device_name` | AXL `name` | Canonical CCM identifier |
| `device_kind` | derived from name prefix | `sep`/`csf`/`tct`/`bot`/`csk`/`ata`/`cti`/`other` |
| `mac_address` | derived (SEP/ATA) or null (softphones) | |
| `description` | AXL `description` | |
| `device_pool` | AXL `devicePoolName` | |
| `common_phone_profile` | AXL `commonPhoneConfigName` | |
| `common_device_configuration` | AXL `commonDeviceConfigName` | |
| `phone_button_template` | AXL `phoneTemplateName` | |
| `softkey_template` | AXL `softkeyTemplateName` | |
| `owner_user_id` | AXL `ownerUserName` | AXL-configured assignee |
| `mobility_user_id` | AXL `mobilityUserIdName` | |
| `built_in_bridge` | AXL `builtInBridgeStatus` | Tri-state: Default/On/Off |
| `privacy` | AXL `callInfoPrivacyStatus` | Tri-state |
| `device_mobility_mode` | AXL `deviceMobilityMode` | |
| `dnd_status` / `dnd_option` | AXL `dndStatus` / `dndOption` | |
| `device_security_profile` | AXL `securityProfileName` | |
| `sip_profile` | AXL `sipProfileName` | |
| `rerouting_css` | AXL `rerouteCallingSearchSpaceName` | Note: AXL drops the "-ing" |
| `subscribe_css` | AXL `subscribeCallingSearchSpaceName` | |
| `mtp_required` | AXL `mtpRequired` | |
| `packet_capture_mode` | AXL `packetCaptureMode` | |
| `ccm_location` | AXL `locationName` | CCM Call Admission Control concept, distinct from physical location |
| `network_location` | AXL `networkLocation` | |
| `active_load` | RIS `ActiveLoadID` | Running firmware (SEP) or Webex/Jabber build (CSF/TCT/BOT) |
| `inactive_load` | RIS `InactiveLoadID` | Rollback target (relevant for IP phones; equal to active for softphones) |
| `live_login_user` | RIS `LoginUserId` | Currently signed-in user |
| `status_reason` | RIS `StatusReason` | Cisco's reason code; UI maps to human label |
| `live_status_polled_at` | (sync timestamp) | When the RIS data was captured |

### Line fields (per-DN-appearance)

| Field | Source | Notes |
|-------|--------|-------|
| `phone`, `directory_number`, `button_index` | identifiers | |
| `label`, `display`, `ring_setting` | AXL `label`/`display`/`ringSetting` | |
| `max_num_calls`, `busy_trigger` | AXL nested line fields | Default 4 / 2 |
| `mwl_policy`, `audible_mwi` | MWI behavior | |
| `recording_flag` | AXL `recordingFlag` | Audit fact for compliance |
| `missed_call_logging` | bool | |
| `partition_usage` | "General" / etc. | |

## Sync ordering (top-level)

DiffSync's `top_level` tuple defines load order, which matters for
identifier resolution (children reference parents by natural key):

1. `phone_system` — root
2. Dial plan: `partition`, `calling_search_space`, `css_partition_membership`
3. Numbers: `directory_number`
4. Endpoints: `phone`
5. Phone children: `line`, `speed_dial`, `busy_lamp_field`, `phone_service_url`
6. Routing: `trunk`, `route_list`, `route_group`, `route_pattern`, `translation_pattern`
7. Analog: `analog_gateway`, `analog_port`

When `enrich_phone_lines=False`, the four "phone child" models are excluded
from the diff so existing records aren't orphan-deleted by a sync that
isn't capable of populating them.
