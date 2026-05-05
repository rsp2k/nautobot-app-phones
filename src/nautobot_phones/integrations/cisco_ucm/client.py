"""AXLClient — zeep-based wrapper around the Cisco UCM AXL SOAP API.

AXL (Administrative XML Layer) is Cisco's authenticated SOAP API for CUCM
configuration. We wrap it in a thin client that:

1. Loads the AXL WSDL from a path supplied by the operator (the WSDL is
   shipped with CUCM under the AXLSQLToolkit; we don't bundle it because
   it's licensed Cisco IP).
2. Authenticates via HTTP Basic over TLS to the publisher node.
3. Caches the WSDL parse output via zeep's SqliteCache for fast re-init.
4. Defensive field access on every response — `getattr(obj, "field", None)`
   — so the client tolerates field additions/removals across AXL versions
   (12.5 / 14 / 15).

Per-version WSDL location is configurable via the `AXL_VERSION` env var
(default `15.0`). The expected directory layout when the WSDL is supplied
is `<wsdl_root>/<version>/AXLAPI.wsdl`, e.g.
`/opt/axl/15.0/AXLAPI.wsdl`.

This client is intentionally read-only — we only call `listX` methods.
The mirror flow doesn't write back to CUCM. If we ever change that, the
write methods (addPhone, updatePhone, removePhone, etc.) live on the same
zeep service and can be added at the bottom of this class.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import zeep
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep.cache import SqliteCache
from zeep.transports import Transport


AXL_DEFAULT_PORT = 8443
AXL_DEFAULT_VERSION = "15.0"
AXL_BINDING = "{http://www.cisco.com/AXLAPIService/}AXLAPIBinding"


class AXLClient:
    """Read-only wrapper around the Cisco UCM AXL SOAP service.

    Parameters:
        host: FQDN or IP of the CUCM publisher (no scheme, no port).
        username: AXL-permissioned account (typically a CUCM application user).
        password: Password for that account.
        wsdl_path: Filesystem path to AXLAPI.wsdl shipped with CUCM. If
            None, looks up `AXL_WSDL_PATH` env var, then falls back to
            `<AXL_WSDL_ROOT>/<version>/AXLAPI.wsdl`.
        version: AXL schema version (default `15.0`). Used for cache key
            isolation and WSDL path defaulting.
        verify_tls: Verify the publisher's TLS cert. Default True; set
            False for lab clusters with self-signed certs.
        timeout: SOAP request timeout in seconds. Default 30.

    Raises:
        FileNotFoundError: WSDL file not found at the resolved path.
        zeep.exceptions.Fault: AXL returned a SOAP fault on a request.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        wsdl_path: Optional[str] = None,
        version: str = AXL_DEFAULT_VERSION,
        verify_tls: bool = True,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.version = version
        self.endpoint = f"https://{host}:{AXL_DEFAULT_PORT}/axl/"

        wsdl_path = wsdl_path or self._resolve_wsdl_path(version)
        if not os.path.isfile(wsdl_path):
            raise FileNotFoundError(
                f"AXL WSDL not found at {wsdl_path!r}. Set AXL_WSDL_PATH or "
                f"place the file at <AXL_WSDL_ROOT>/{version}/AXLAPI.wsdl. "
                "WSDLs ship with CUCM under the AXLSQLToolkit; download from "
                "the publisher's plugin page."
            )

        session = Session()
        session.verify = verify_tls
        session.auth = HTTPBasicAuth(username, password)
        cache = SqliteCache(path=f"/tmp/axl-wsdl-cache-{version}.db", timeout=60 * 60 * 24)
        transport = Transport(session=session, cache=cache, timeout=timeout)

        self._client = zeep.Client(wsdl=wsdl_path, transport=transport)
        self._service = self._client.create_service(AXL_BINDING, self.endpoint)

    @staticmethod
    def _resolve_wsdl_path(version: str) -> str:
        """Pick the WSDL path from env vars with a sane default."""
        if env_path := os.environ.get("AXL_WSDL_PATH"):
            return env_path
        root = os.environ.get("AXL_WSDL_ROOT", "/opt/axl")
        return os.path.join(root, version, "AXLAPI.wsdl")

    # -- Read-only AXL list methods ------------------------------------------
    #
    # Each method calls one CUCM `listX` operation. AXL requires both a
    # `searchCriteria` dict (use `{"name": "%"}` for "all") AND a
    # `returnedTags` dict (enumerates the fields to return on each row).
    # `returnedTags` is REQUIRED — empty dict gives empty rows, so each
    # method declares a default tag set tuned to what our adapter needs.

    # Per-operation defaults for AXL request shapes. Each op has different
    # valid fields for both `searchCriteria` (filter) and `returnedTags`
    # (which scalar fields come back). Discovered empirically via AXL 15.0
    # schema errors — values reflect what the server actually accepts.
    #
    # Note: complex/nested fields (registration status, SIP trunk
    # destinations, line membership lists) are NOT available via listX;
    # they require per-record getX calls. v1 syncs the listX subset.

    _DEFAULT_SEARCH: dict[str, dict] = {
        # Most ops use `name` as the wildcard key.
        "listRoutePartition": {"name": "%"},
        "listCss": {"name": "%"},
        "listPhone": {"name": "%"},
        "listSipTrunk": {"name": "%"},
        "listRouteList": {"name": "%"},
        "listRouteGroup": {"name": "%"},
        # These ops use a different identifier:
        "listLine": {"pattern": "%"},
        "listRoutePattern": {"pattern": "%"},
        "listTransPattern": {"pattern": "%"},
        "listGateway": {"domainName": "%"},
    }

    # AXL FK-type fields (XFkType) require an explicit sub-tag dict to return
    # the actual referenced value — empty string at top level just gets you
    # an empty wrapper. Pattern: {"_value_1": "", "uuid": ""} returns both
    # the human-readable name and the GUID reference.
    _FK_TAG = {"_value_1": "", "uuid": ""}

    _DEFAULT_TAGS: dict[str, dict] = {
        "listRoutePartition": {"name": "", "description": ""},
        "listCss": {"name": "", "description": ""},
        "listLine": {
            "pattern": "",
            "description": "",
            "alertingName": "",
            "routePartitionName": _FK_TAG,
            "voiceMailProfileName": _FK_TAG,
        },
        # listPhone exposes a wide subset of getPhone scalars — pulling them
        # all up here means the cheap bulk sync gets full Device Info +
        # Protocol Specific fidelity without paying for per-phone getPhone.
        # Nested arrays (lines/speeddials/busyLampFields/services) still
        # need getPhone — covered by the enrich_phone_lines flag.
        "listPhone": {
            "name": "",
            "description": "",
            "product": "",
            "model": "",
            # NB: `currentRegistrationStatus` is NOT a valid listPhone tag —
            # CCM tracks live registration server-side via RisPort70, not in
            # the configuration store that AXL exposes. We get it from the
            # RisPort70 status_map populated alongside the IP map.
            # Device Information
            "devicePoolName": _FK_TAG,
            "commonPhoneConfigName": _FK_TAG,
            "commonDeviceConfigName": _FK_TAG,
            "phoneTemplateName": _FK_TAG,
            "softkeyTemplateName": _FK_TAG,
            "ownerUserName": _FK_TAG,
            "mobilityUserIdName": _FK_TAG,
            "builtInBridgeStatus": "",
            "callInfoPrivacyStatus": "",
            "deviceMobilityMode": "",
            "alwaysUsePrimeLine": "",
            "alwaysUsePrimeLineForVoiceMessage": "",
            "userLocale": "",
            "networkLocale": "",
            "aarNeighborhoodName": _FK_TAG,
            "dndStatus": "",
            "dndOption": "",
            # Protocol Specific Information
            "securityProfileName": _FK_TAG,
            "sipProfileName": _FK_TAG,
            "rerouteCallingSearchSpaceName": _FK_TAG,  # NB: no '-ing' suffix in AXL
            "subscribeCallingSearchSpaceName": _FK_TAG,
            "mtpRequired": "",
            "packetCaptureMode": "",
        },
        "listSipTrunk": {
            "name": "",
            "description": "",
        },
        "listRoutePattern": {
            "pattern": "",
            "description": "",
            "routePartitionName": _FK_TAG,
            "patternUrgency": "",
        },
        # Translation Patterns: full Pattern Definition + Calling/Called Party
        # Transformation field set. The CCM admin form groups these into three
        # sections; we mirror that. Long-tail fields (presentation bits,
        # numbering plans, number types) come back too — the adapter routes
        # them into vendor_extras for fidelity without polluting the schema.
        "listTransPattern": {
            "pattern": "",
            "description": "",
            "usage": "",
            "routePartitionName": _FK_TAG,
            "callingSearchSpaceName": _FK_TAG,
            # Pattern Definition
            "blockEnable": "",
            "releaseClause": "",
            "patternUrgency": "",
            "provideOutsideDialtone": "",
            "useOriginatorCss": "",
            "dontWaitForIDTOnSubsequentHops": "",
            "routeNextHopByCgpn": "",
            "isEmergencyServiceNumber": "",
            "routeClass": "",
            # Calling Party Transformations
            "useCallingPartyPhoneMask": "",
            "callingPartyTransformationMask": "",
            "callingPartyPrefixDigits": "",
            "callingLinePresentationBit": "",
            "callingNamePresentationBit": "",
            "callingPartyNumberType": "",
            "callingPartyNumberingPlan": "",
            # Connected Party Transformations (long-tail → vendor_extras)
            "connectedLinePresentationBit": "",
            "connectedNamePresentationBit": "",
            # Called Party Transformations
            "digitDiscardInstructionName": _FK_TAG,
            "calledPartyTransformationMask": "",
            "prefixDigitsOut": "",
            "calledPartyNumberType": "",
            "calledPartyNumberingPlan": "",
        },
        "listGateway": {
            "domainName": "",
            "description": "",
            "product": "",
            "protocol": "",
        },
        "listRouteList": {
            "name": "",
            "description": "",
        },
        "listRouteGroup": {
            "name": "",
            "distributionAlgorithm": "",
        },
    }

    def list_phones(self, **overrides) -> list[Any]:
        """`listPhone` — registered phone devices."""
        return self._list("listPhone", "phone", **overrides)

    def list_lines(self, **overrides) -> list[Any]:
        """`listLine` — directory numbers (DNs in CUCM terminology).

        NOTE: AXL's `Line` object IS a DN. Our app's Line model is something
        different (a phone-button appearance). Don't confuse the two.
        """
        return self._list("listLine", "line", **overrides)

    def list_route_partitions(self, **overrides) -> list[Any]:
        """`listRoutePartition` — partitions in our model."""
        return self._list("listRoutePartition", "routePartition", **overrides)

    def list_css(self, **overrides) -> list[Any]:
        """`listCss` — calling search spaces."""
        return self._list("listCss", "css", **overrides)

    def list_sip_trunks(self, **overrides) -> list[Any]:
        """`listSipTrunk` — SIP trunks."""
        return self._list("listSipTrunk", "sipTrunk", **overrides)

    def list_route_patterns(self, **overrides) -> list[Any]:
        """`listRoutePattern` — outbound routing patterns."""
        return self._list("listRoutePattern", "routePattern", **overrides)

    def list_translation_patterns(self, **overrides) -> list[Any]:
        """`listTransPattern` — digit translation patterns."""
        return self._list("listTransPattern", "transPattern", **overrides)

    def list_gateways(self, **overrides) -> list[Any]:
        """`listGateway` — analog gateways (MGCP/SIP/SCCP)."""
        return self._list("listGateway", "gateway", **overrides)

    def list_route_lists(self, **overrides) -> list[Any]:
        """`listRouteList` — Route Lists."""
        return self._list("listRouteList", "routeList", **overrides)

    def list_route_groups(self, **overrides) -> list[Any]:
        """`listRouteGroup` — Route Groups."""
        return self._list("listRouteGroup", "routeGroup", **overrides)

    # -- Per-record getX methods ---------------------------------------------
    #
    # AXL list operations return scalar fields only. Complex/nested data
    # (phone-button line membership, route-group members, full SIP trunk
    # destinations, etc.) requires per-record getX. Slow for bulk —
    # ~200-400ms per call.

    def get_phone(self, name: str) -> Any:
        """`getPhone` — full phone record including the nested `lines` array.

        Returns the inner phone object (already unwrapped from the SOAP
        envelope). Caller checks for None on missing fields via getattr.
        """
        result = self._service.getPhone(name=name)
        # zeep wraps the SOAP `return` element. `return` is a Python keyword
        # so attribute access requires getattr.
        return_obj = getattr(result, "return")
        return getattr(return_obj, "phone", None) if return_obj is not None else None

    def _list(
        self,
        operation: str,
        result_key: str,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """Internal: call a `listX` operation and unwrap the result.

        Per-operation defaults for `returned_tags` come from `_DEFAULT_TAGS`
        — callers can override by passing a custom dict to override the
        full set or `search_criteria` to scope to a subset.
        """
        op = getattr(self._service, operation)
        criteria = search_criteria if search_criteria is not None else self._DEFAULT_SEARCH.get(operation, {"name": "%"})
        tags = returned_tags if returned_tags is not None else self._DEFAULT_TAGS.get(operation, {"name": ""})
        response = op(searchCriteria=criteria, returnedTags=tags)
        # AXL list responses: {"return": {<result_key>: [row, row, ...]}}.
        # When zero rows match, the inner key may be missing entirely.
        return_obj = getattr(response, "return_", None) or getattr(response, "return", None)
        if return_obj is None:
            return []
        rows = getattr(return_obj, result_key, None)
        return rows or []
