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
    # Each method calls one CUCM `listX` operation. AXL list operations
    # require a `searchCriteria` dict (use `{"name": "%"}` for "all") and
    # an optional `returnedTags` dict (controls which fields come back).
    # We default to "all rows, all fields" — adapter callers can override.

    def list_phones(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listPhone` — registered phone devices."""
        return self._list("listPhone", "phone", search_criteria, returned_tags)

    def list_lines(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listLine` — directory numbers (DNs) in CUCM terminology.

        NOTE: AXL's `Line` object IS a DN. Our app's Line model is something
        different (a phone-button appearance). Don't confuse the two.
        """
        return self._list("listLine", "line", search_criteria, returned_tags)

    def list_route_partitions(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listRoutePartition` — partitions in our model."""
        return self._list("listRoutePartition", "routePartition", search_criteria, returned_tags)

    def list_css(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listCss` — calling search spaces."""
        return self._list("listCss", "css", search_criteria, returned_tags)

    def list_sip_trunks(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listSipTrunk` — SIP trunks."""
        return self._list("listSipTrunk", "sipTrunk", search_criteria, returned_tags)

    def list_route_patterns(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listRoutePattern` — outbound routing patterns."""
        return self._list("listRoutePattern", "routePattern", search_criteria, returned_tags)

    def list_gateways(
        self,
        search_criteria: Optional[dict] = None,
        returned_tags: Optional[dict] = None,
    ) -> list[Any]:
        """`listGateway` — analog gateways (MGCP/SIP/SCCP)."""
        return self._list("listGateway", "gateway", search_criteria, returned_tags)

    def _list(
        self,
        operation: str,
        result_key: str,
        search_criteria: Optional[dict],
        returned_tags: Optional[dict],
    ) -> list[Any]:
        """Internal: call a `listX` operation and unwrap the result.

        AXL list responses are shaped `{"return": {<result_key>: [...]}}`,
        but if zero rows match, the inner key may be missing entirely.
        Handle both shapes defensively.
        """
        op = getattr(self._service, operation)
        response = op(
            searchCriteria=search_criteria or {"name": "%"},
            returnedTags=returned_tags,
        )
        return getattr(getattr(response, "return_", None) or response.get("return", {}), result_key, []) or []
