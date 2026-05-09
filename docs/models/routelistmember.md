# RouteListMember

Through-table joining [RouteList](routelist.md) and [RouteGroup](routegroup.md). The `priority` column controls evaluation order in the route-list.

| Field | Description |
|-------|-------------|
| `route_list` | FK to [RouteList](routelist.md) |
| `route_group` | FK to [RouteGroup](routegroup.md) |
| `priority` | Integer — lower numbers evaluated first |

**Natural key:** (`route_list`, `route_group`).

**Base class:** `BaseModel`.

**Relationships:** Pure junction; renders as a nested panel on RouteList detail.

::: nautobot_phones.models.RouteListMember
    options:
      show_root_heading: false
      heading_level: 2
