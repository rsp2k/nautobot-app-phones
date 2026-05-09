# HuntListMember

Through-table joining HuntList ↔ LineGroup. The `selection_order` column controls priority across LineGroups within the same HuntList.

| Field | Description |
|-------|-------------|
| `hunt_list` | FK to [HuntList](huntlist.md) |
| `line_group` | FK to [LineGroup](linegroup.md) |
| `selection_order` | Integer — lower numbers evaluated first |

**Natural key:** (`hunt_list`, `line_group`).

**Base class:** `BaseModel`.

**Relationships:** Pure junction; renders as a nested panel on HuntList detail.

::: nautobot_phones.models.HuntListMember
    options:
      show_root_heading: false
      heading_level: 2
