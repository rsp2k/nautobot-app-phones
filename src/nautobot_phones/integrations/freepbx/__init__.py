"""FreePBX 17 integration via the GraphQL API.

Mirrors the cisco_ucm package shape (client / adapter / jobs) so
operators familiar with one adapter can navigate the other. The
underlying protocols are different (SOAP/AXL for CCM, REST+GraphQL
for FreePBX) but the DiffSync model output is identical — both
adapters populate the same vendor-agnostic Nautobot phones schema.
"""
