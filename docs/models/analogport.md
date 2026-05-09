# AnalogPort

A single FXS or FXO port on an [AnalogGateway](analoggateway.md). FXS ports terminate analog phones (and bind to a [DirectoryNumber](directorynumber.md)); FXO ports terminate inbound POTS lines from the carrier.

| Field | Description |
|-------|-------------|
| `gateway` | FK to [AnalogGateway](analoggateway.md) |
| `port_index` | Hex-encoded slot/subslot/port (decoded by adapter) |
| `port_type` | fxs / fxo |
| `directory_number` | FK to [DirectoryNumber](directorynumber.md), nullable (FXS only) |

**Natural key:** (`gateway`, `port_index`).

**Base class:** `BaseModel`.

**Relationships:** Belongs to [AnalogGateway](analoggateway.md). FXS ports may bind to a [DirectoryNumber](directorynumber.md).

::: nautobot_phones.models.AnalogPort
    options:
      show_root_heading: false
      heading_level: 2
