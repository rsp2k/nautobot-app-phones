# RouteList

An ordered priority list of [RouteGroups](routegroup.md). Route patterns target a RouteList, which evaluates its member groups in priority order — the first group with an available device handles the call.

| Field | Description |
|-------|-------------|
| `name` | RouteList name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `description` | Free-form |
| `vendor_extras` | JSONField |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Members are [RouteGroups](routegroup.md) via [RouteListMember](routelistmember.md). Targeted by [RoutePattern.target_route_list](routepattern.md).

::: nautobot_phones.models.RouteList
    options:
      show_root_heading: false
      heading_level: 2
