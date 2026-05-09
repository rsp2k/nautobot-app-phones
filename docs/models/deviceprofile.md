# DeviceProfile

A vendor-agnostic name for a named bundle of device-config defaults applied to phones referencing it. Maps to CCM DevicePool / FreePBX device template / similar.

| Field | Description |
|-------|-------------|
| `name` | Profile name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `description` | Free-form |
| `vendor_extras` | JSONField — CCM bundles: `callManagerGroupName`, `regionName`, `locationName`, `dateTimeSettingName`, `srstName`, `mediaResourceListName`, `networkLocale`, etc. |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Referenced by [Phone.device_profile](phone.md).

::: nautobot_phones.models.DeviceProfile
    options:
      show_root_heading: false
      heading_level: 2
