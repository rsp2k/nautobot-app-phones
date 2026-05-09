# DIDBlock

An E.164 number range purchased from a carrier. Validated for equal-length endpoints, same prefix, start ≤ end. Individual DIDs are NOT materialized until they're assigned — see [DID](did.md).

| Field | Description |
|-------|-------------|
| `start_e164` | First E.164 number in range |
| `end_e164` | Last E.164 number in range |
| `carrier` | FK to [Carrier](carrier.md) |
| `location` | FK to `dcim.Location` |
| `phone_system` | FK to [PhoneSystem](phonesystem.md), nullable |
| `description` | Free-form description |
| `size` | Computed property — `int(end) - int(start) + 1` |

**Natural key:** (`start_e164`, `end_e164`, `carrier`).

**Base class:** `PrimaryModel`.

**Relationships:** Parent of [DID](did.md) records that have been materialized.

::: nautobot_phones.models.DIDBlock
    options:
      show_root_heading: false
      heading_level: 2
