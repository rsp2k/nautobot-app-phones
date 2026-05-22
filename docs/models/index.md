# Models

Per-model reference pages. Each page covers natural keys, relationships,
and vendor-specific data conventions for one Nautobot model.

## System

- [PhoneSystem](phonesystem.md) — cluster root; one record per CCM cluster or FreePBX install
- [SipCircuitProfile](sipcircuitprofile.md) — SIP-specific extension on `circuits.Circuit` (sessions, pilot, OLI/CLID policy, cut-sheet metadata)

## Dial plan

- [Partition](partition.md) — routing namespace (CCM Partition / FreePBX context)
- [CallingSearchSpace](callingsearchspace.md) — ordered list of partitions visible to a caller
- [CSSPartitionMembership](csspartitionmembership.md) — through-table for CSS ↔ Partition

## Numbers

- [DirectoryNumber](directorynumber.md) — extension within a partition
- [DIDBlock](didblock.md) — E.164 number ranges delivered by a `circuits.Provider`, optionally attached to a specific `circuits.Circuit`
- [DID](did.md) — individual E.164 number; materialized on assignment or for sparse one-offs not in any block
- [DIDAssignment](didassignment.md) — links a DID to a target (DN, Trunk, future voicemail)

## Endpoints

- [Phone](phone.md) — any phone-class endpoint (IP phones, Jabber, ATAs, CTI ports)
- [Line](line.md) — DN appearance on a phone button
- [SpeedDial](speeddial.md) — speed-dial button
- [BusyLampField](busylampfield.md) — presence-aware speed-dial
- [PhoneServiceUrl](phoneserviceurl.md) — service-launching button (XML services / HTTP softkeys)

## Routing

- [Trunk](trunk.md) — egress paths (SIP/PRI/H323/MGCP)
- [RouteList](routelist.md) — ordered priority list of route groups
- [RouteGroup](routegroup.md) — load-balanced trunk group
- [RouteListMember](routelistmember.md) — RouteList ↔ RouteGroup through-table
- [RouteGroupMember](routegroupmember.md) — RouteGroup ↔ Trunk/Gateway through-table
- [RoutePattern](routepattern.md) — outbound dial-plan match (XOR target_trunk/target_route_list/target_dn)
- [TranslationPattern](translationpattern.md) — pre-routing digit rewrite

## Hunt subsystem

- [HuntPilot](huntpilot.md) — pattern that fronts a HuntList
- [HuntList](huntlist.md) — ordered set of LineGroups
- [LineGroup](linegroup.md) — ordered set of DNs with a hunt algorithm
- [HuntListMember](huntlistmember.md) — HuntList ↔ LineGroup through-table
- [LineGroupMember](linegroupmember.md) — LineGroup ↔ DirectoryNumber through-table

## Analog

- [AnalogGateway](analoggateway.md) — VG450 / VG350 / etc.
- [AnalogPort](analogport.md) — FXS/FXO port on a gateway

## Feature config (vendor-agnostic)

- [DeviceProfile](deviceprofile.md) — named bundle of device-config defaults (CCM DevicePool / FreePBX template)
- [VoicemailProfile](voicemailprofile.md) — voicemail box config
- [CallPickupGroup](callpickupgroup.md) — pattern that picks up ringing peers
- [CallPickupGroupMember](callpickupgroupmember.md) — CallPickupGroup ↔ DirectoryNumber through-table

## Vendor-specific data: `vendor_extras`

Every `PrimaryModel` carries a `vendor_extras: JSONField` for fields not
promoted to columns. CCM-specific keys preserve the AXL camelCase name
for traceability with the CCM admin UI; a FreePBX adapter populates
its own dialect under different keys without schema churn.

Filter via Nautobot's standard JSON filtering:

```
/plugins/phones/phones/?vendor_extras__axl_model=Cisco%207841
```
