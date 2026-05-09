# HuntPilot

A pattern dialed to enter a HuntList — e.g. `1204` → ring the HIM team. The pilot fronts a [HuntList](huntlist.md), which holds the prioritized [LineGroups](linegroup.md).

| Field | Description |
|-------|-------------|
| `pattern` | Dialed-digit pattern |
| `partition` | FK to [Partition](partition.md) |
| `description` | Free-form |
| `hunt_list` | FK to [HuntList](huntlist.md) |
| `alerting_name` | Display name shown to ringing members |
| `max_hunt_duration` | Seconds before forwarding kicks in |
| `forward_hunt_no_answer_destination` | Destination if nobody answers |
| `forward_hunt_busy_destination` | Destination if all groups busy |

**Natural key:** (`partition`, `pattern`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [Partition](partition.md). Targets a [HuntList](huntlist.md).

::: nautobot_phones.models.HuntPilot
    options:
      show_root_heading: false
      heading_level: 2
