# RouteGroupMember

Through-table joining [RouteGroup](routegroup.md) to its members. Target uses a GenericForeignKey so a RouteGroup can hold either Trunks or AnalogGateways without column proliferation.

| Field | Description |
|-------|-------------|
| `route_group` | FK to [RouteGroup](routegroup.md) |
| `target_type` | ContentType — Trunk or AnalogGateway |
| `target_id` | UUID |
| `priority` | Integer |

**Natural key:** (`route_group`, target GFK).

**Base class:** `BaseModel`.

**Relationships:** Pure junction; renders as a nested panel on RouteGroup detail.

::: nautobot_phones.models.RouteGroupMember
    options:
      show_root_heading: false
      heading_level: 2
