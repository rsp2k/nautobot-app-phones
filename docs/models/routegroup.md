# RouteGroup

A load-balanced trunk group. Members are [Trunks](trunk.md) (or [AnalogGateways](analoggateway.md)); the `distribution_algorithm` decides which member handles the call.

| Field | Description |
|-------|-------------|
| `name` | RouteGroup name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `distribution_algorithm` | top_down / circular / longest_idle / longest_unused / etc. |
| `description` | Free-form |
| `vendor_extras` | JSONField |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Members are [Trunks](trunk.md) / [AnalogGateways](analoggateway.md) via [RouteGroupMember](routegroupmember.md). Referenced by [RouteListMember](routelistmember.md).

::: nautobot_phones.models.RouteGroup
    options:
      show_root_heading: false
      heading_level: 2
