# Phone

Any phone-class endpoint — IP phones (SEP), Jabber softphones (CSF/TCT/BOT), ATAs, CCX/CER/CTI ports, and FreePBX SIP/PJSIP peers. ATAs use this model with `device_kind=ata` and analog ports as separate AnalogPort records.

| Field | Description |
|-------|-------------|
| `device_name` | Vendor-side device name (CCM `SEP<MAC>` etc., FreePBX `PJSIP/<ext>`) |
| `device_kind` | Endpoint type — see [PhoneDeviceKindChoices](../user/sync_reference.md) |
| `mac_address` | MACAddressField, nullable (softphones have none) |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `device` | FK to `dcim.Device`, nullable — DCIM is authoritative for hardware |
| `device_profile` | FK to [DeviceProfile](deviceprofile.md), nullable |
| `media_zone` | Vendor-agnostic media-admission boundary (CCM Location / Avaya Network Region) |
| `registration_status` | registered / unregistered / partially_registered / unknown |
| `active_load / inactive_load` | Currently-running firmware (RisPort70 enrichment) |
| `dnd_status` | Do Not Disturb on/off |
| `vendor_extras` | JSONField — long-tail vendor config |

**Natural key:** (`phone_system`, `device_name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Has [Lines](line.md), [SpeedDials](speeddial.md), [BusyLampFields](busylampfield.md), [PhoneServiceUrls](phoneserviceurl.md). Optionally linked to a `dcim.Device`.

::: nautobot_phones.models.Phone
    options:
      show_root_heading: false
      heading_level: 2
