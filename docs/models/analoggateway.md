# AnalogGateway

A Cisco voice gateway (VG450, VG350, VG310, etc.) hosting analog ports for fax machines, overhead paging, elevator phones, etc.

| Field | Description |
|-------|-------------|
| `name` | Gateway name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `location` | FK to `dcim.Location` |
| `device` | FK to `dcim.Device`, nullable |
| `model` | Hardware model string |
| `protocol` | mgcp / sip / sccp |
| `vendor_extras` | JSONField — `module_units` describes installed FXS/FXO cards |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Has [AnalogPorts](analogport.md). Optionally linked to a `dcim.Device`.

::: nautobot_phones.models.AnalogGateway
    options:
      show_root_heading: false
      heading_level: 2
