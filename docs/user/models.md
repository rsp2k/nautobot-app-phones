# Model Reference

Quick reference for the model graph. Each row links to the relevant
section of the [Sync Reference](sync_reference.md) for field details.

## Identity table

| Model | Base class | Natural key | Notes |
|-------|-----------|-------------|-------|
| `PhoneSystem` | `PrimaryModel` | `name` | Cluster root |
| `Carrier` | `OrganizationalModel` | `name` | Telecom provider |
| `Partition` | `OrganizationalModel` | (`phone_system`, `name`) | Routing namespace |
| `CallingSearchSpace` | `OrganizationalModel` | (`phone_system`, `name`) | Ordered list of partitions |
| `CSSPartitionMembership` | `BaseModel` | (`css`, `partition`) + `priority` | Through-table |
| `DirectoryNumber` | `PrimaryModel` | (`partition`, `extension`) | DN |
| `DIDBlock` | `PrimaryModel` | (`start_e164`, `end_e164`, `carrier`) | E.164 ranges |
| `DID` | `PrimaryModel` | `e164` | Materialized only on assignment |
| `DIDAssignment` | `BaseModel` | OneToOne `did` + GFK target | Generic FK to DN/Trunk |
| `Phone` | `PrimaryModel` | (`phone_system`, `device_name`) | Any phone-class endpoint |
| `Line` | `BaseModel` | (`phone`, `button_index`) | DN appearance |
| `SpeedDial` | `BaseModel` | (`phone`, `button_index`) | Speed-dial button |
| `BusyLampField` | `BaseModel` | (`phone`, `button_index`) | Presence-aware speed-dial |
| `PhoneServiceUrl` | `BaseModel` | (`phone`, `button_index`) | XML service button |
| `Trunk` | `PrimaryModel` | (`phone_system`, `name`) | SIP/PRI/H323/MGCP |
| `RoutePattern` | `PrimaryModel` | (`partition`, `pattern`) | XOR target_trunk/target_route_list/target_dn |
| `RouteList` | `PrimaryModel` | (`phone_system`, `name`) | Priority list of route groups |
| `RouteGroup` | `PrimaryModel` | (`phone_system`, `name`) | Load-balanced trunk group |
| `RouteListMember` | `BaseModel` | (`route_list`, `route_group`) | Through-table with priority |
| `RouteGroupMember` | `BaseModel` | (`route_group`, target GFK) | Through-table |
| `TranslationPattern` | `PrimaryModel` | (`partition`, `pattern`) | Pre-routing digit rewrite |
| `AnalogGateway` | `PrimaryModel` | (`phone_system`, `name`) | VG450/VG350/etc. |
| `AnalogPort` | `BaseModel` | (`gateway`, `port_index`) | FXS/FXO port |

## Vendor-specific data: `vendor_extras` JSONField

Every `PrimaryModel` carries a `vendor_extras: JSONField`. This holds
CCM-specific fields not modeled as columns. Examples:

| Model | Common contents |
|-------|----------------|
| `Phone` | `axl_model` (used by device-creation pass to find DeviceType) |
| `AnalogGateway` | `module_units` (list of `{unit_index, subunit_index, subunit_product}` dicts) |
| `RoutePattern` | (currently empty by default) |
| `TranslationPattern` | Long-tail Cisco fields (presentation bits, numbering plans, number types) |

Filterable via Nautobot's standard JSON filtering:

```
/plugins/phones/phones/?vendor_extras__axl_model=Cisco%207841
```

## Phone @property accessors

`Phone` exposes two computed properties that read through the linked
`dcim.Device`:

- **`Phone.model`** — reads `self.device.device_type.model` (falls back
  to `vendor_extras['axl_model']` when no Device is linked yet)
- **`Phone.location`** — reads `self.device.location` (falls back to
  None)

This makes Nautobot's DCIM the single source of truth for hardware
identity and physical placement, while the Phone record stays focused
on CCM-side concerns.
