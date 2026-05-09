# Trunk

An egress path from the phone system. Vendor-agnostic `trunk_type` covers SIP / PRI / H.323 / MGCP — original FreePBX `tech` (pjsip/iax2/dahdi) preserved in vendor_extras.

| Field | Description |
|-------|-------------|
| `name` | Trunk name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `trunk_type` | sip / pri / h323 / mgcp |
| `destination_address` | Endpoint URL or address |
| `destination_port` | Integer, nullable |
| `vendor_extras` | JSONField — provider, channelid, freepbx_tech, etc. |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Referenced by [RouteGroup](routegroup.md) (membership) and [RoutePattern](routepattern.md) (direct trunk targeting).

::: nautobot_phones.models.Trunk
    options:
      show_root_heading: false
      heading_level: 2
