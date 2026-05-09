# RoutePattern

Outbound dial-plan match. When a caller dials digits matching the `pattern`, the call routes to exactly one of: a Trunk, a RouteList, or a DirectoryNumber. A DB CHECK constraint enforces the XOR.

| Field | Description |
|-------|-------------|
| `pattern` | Dialed-digit pattern (CCM wildcards: X, [n-m], !, .) |
| `partition` | FK to [Partition](partition.md) |
| `css` | FK to [CallingSearchSpace](callingsearchspace.md), nullable |
| `target_trunk` | FK to [Trunk](trunk.md), nullable |
| `target_route_list` | FK to [RouteList](routelist.md), nullable |
| `target_dn` | FK to [DirectoryNumber](directorynumber.md), nullable |
| `urgent` | Match-and-route immediately, don't wait for inter-digit timeout |
| `discard_digits` | Pre-Dot / digit-strip rule |

**Natural key:** (`partition`, `pattern`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [Partition](partition.md). Targets exactly one of [Trunk](trunk.md), [RouteList](routelist.md), or [DirectoryNumber](directorynumber.md).

::: nautobot_phones.models.RoutePattern
    options:
      show_root_heading: false
      heading_level: 2
