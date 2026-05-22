"""HTTP client for the FreePBX 17 GraphQL API.

FreePBX 17's API ships as two separable modules: `api` (the OAuth2 server
+ scope/permission model) and the actual GraphQL endpoint at
``/admin/api/api/graphql``. To use it you create an "Application" in the
FreePBX admin UI under Admin > API > Applications, which gives you a
``client_id`` + ``client_secret`` for the OAuth2 client_credentials flow.

The client here:
  - Acquires a bearer token via client_credentials (cached until expiry).
  - Issues GraphQL queries against ``/admin/api/api/graphql``.
  - Uses ``httpx`` (sync mode — Nautobot SSoT jobs are blocking).
  - Tolerates schema drift across FreePBX patch versions: callers should
    use ``.get()``-style access on results, since the schema isn't 100%
    stable across betas.

This is intentionally minimal — the adapter does the heavy lifting of
mapping FreePBX records into our DiffSync models. See ``FreePBXClient``
below for full constructor parameter docs.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import httpx


class FreePBXAuthError(RuntimeError):
    """Raised when the OAuth2 token request fails."""


class FreePBXAPIError(RuntimeError):
    """Raised when the GraphQL endpoint returns an HTTP or GraphQL error."""


class FreePBXClient:
    """Read-only wrapper around the FreePBX 17 GraphQL API.

    Caches the OAuth2 access token until ~30s before expiry, then
    re-acquires. Re-use a single client across many queries within a
    sync run — token reuse keeps the workload off the FreePBX auth path.
    """

    TOKEN_PATH = "/admin/api/api/token"
    # Confirmed against FreePBX 17.0.21: the path is `/gql`, not `/graphql`.
    # `genclientcred` reports both "graphql_url" and "gql_url" but only the
    # latter actually serves; the former returns 403 even with a valid token.
    GRAPHQL_PATH = "/admin/api/api/gql"
    # Refresh slightly before token expiry to avoid mid-flight 401s.
    TOKEN_RENEW_SECONDS_BEFORE_EXPIRY = 30

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        verify_tls: bool = True,
        timeout: int = 30,
        db_host: Optional[str] = None,
        db_port: int = 3306,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None,
        db_name: str = "asterisk",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.Client(verify=verify_tls, timeout=timeout)
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        # MariaDB direct-query support — required for trunks + outbound routes
        # which aren't (yet) exposed via the api module's GraphQL schema. All
        # queries are SELECT-only; we never write through this connection.
        # Disabled if db_host is None — the adapter falls back to empty
        # results and logs a warning.
        self.db_host = db_host
        self.db_port = db_port
        self.db_user = db_user
        self.db_password = db_password
        self.db_name = db_name

    def __enter__(self) -> "FreePBXClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        """Release the underlying HTTP connection pool."""
        self._http.close()

    # ---------------------------------------------------------------- auth

    def _ensure_token(self) -> str:
        """Return a valid bearer token, refreshing if needed."""
        now = time.time()
        if self._token and now < (self._token_expires_at - self.TOKEN_RENEW_SECONDS_BEFORE_EXPIRY):
            return self._token

        resp = self._http.post(
            f"{self.base_url}{self.TOKEN_PATH}",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        if resp.status_code != 200:
            raise FreePBXAuthError(
                f"Token request failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        body = resp.json()
        self._token = body["access_token"]
        # FreePBX returns expires_in as seconds; default to 1h if missing.
        self._token_expires_at = now + int(body.get("expires_in", 3600))
        return self._token

    # ---------------------------------------------------------------- query

    def query(self, gql: str, variables: Optional[dict] = None) -> dict:
        """Run a GraphQL query and return the ``data`` block.

        Raises FreePBXAPIError on non-200 HTTP, OR when the GraphQL
        response contains an ``errors`` array. Callers get the unwrapped
        ``data`` dict on success.
        """
        token = self._ensure_token()
        resp = self._http.post(
            f"{self.base_url}{self.GRAPHQL_PATH}",
            json={"query": gql, "variables": variables or {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            raise FreePBXAPIError(
                f"GraphQL request failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        body = resp.json()
        if "errors" in body and body["errors"]:
            raise FreePBXAPIError(f"GraphQL errors: {body['errors']}")
        return body.get("data", {}) or {}

    # ----------------------------------------------------------- convenience

    def list_extensions(self) -> list[dict]:
        """Fetch all extensions (PJSIP/SIP/IAX2/etc.).

        Schema confirmed against FreePBX 17.0.21 + api module 17.0.6:

          fetchAllExtensions (Connection wrapper) {
            totalCount, extension[] {
              id, extensionId, tech,
              user { extension, name, voicemail, outboundCid, ... },
              coreDevice { dial, devicetype, description, emergencyCid, ... }
            }
          }

        Caller flattens the nested user/coreDevice into a single dict
        per extension since our DiffSync models don't care about the
        FreePBX-internal split.
        """
        gql = """
        query {
          fetchAllExtensions {
            totalCount
            extension {
              id
              extensionId
              tech
              user {
                extension
                name
                voicemail
                outboundCid
                ringtimer
                noanswerDestination
                busyDestination
                chanunavailDestination
                mohclass
                callwaiting
                recording_priority
              }
              coreDevice {
                dial
                devicetype
                description
                emergencyCid
              }
            }
          }
        }
        """
        data = self.query(gql)
        wrapper = data.get("fetchAllExtensions") or {}
        return wrapper.get("extension") or []

    def list_ring_groups(self) -> list[dict]:
        """Fetch ring groups via direct MariaDB query.

        FreePBX 17's `api` module 17.0.6 doesn't expose ring groups via
        GraphQL — they live in the `ringgroups` table (FreePBX 13+).
        Read-only SELECT; we never write through this connection.

        Returns one dict per ring group with: grpnum, strategy, grptime,
        grplist (hyphen-separated extension list), description, plus
        the behavior flags (cwignore, cfignore, cpickup, recording,
        ringing, alertinfo).
        """
        if not self.db_host:
            return []
        with self._db_cursor() as cur:
            cur.execute(
                "SELECT grpnum, strategy, grptime, grplist, description, "
                "       alertinfo, ringing, cwignore, cfignore, cpickup, "
                "       recording, progress, elsewhere, rvolume "
                "FROM ringgroups ORDER BY grpnum"
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def list_pickup_groups(self) -> list[dict]:
        """Fetch named pickup-group memberships.

        STUB. FreePBX 17's `api` module 17.0.6 doesn't expose
        ``namedcallgroup`` / ``namedpickupgroup`` in either the
        ``fetchExtension`` query or the ``updateExtension`` mutation,
        and the canonical FreePBX-side storage (kvstore_FreePBX_modules_Core
        + extension-edit UI form state) is not directly queryable
        without driving the admin UI. The values DO appear in the
        generated /etc/asterisk/pjsip.endpoint.conf after a fwconsole
        reload, but reading container files from Nautobot is a heavier
        coupling than we want.

        Returns an empty list — adapter callers should handle gracefully.
        Revisit when Sangoma exposes pickup groups via the API module,
        or when operators show enough demand to justify the file-read
        coupling.
        """
        return []

    def list_inbound_routes(self) -> list[dict]:
        """Fetch all inbound routes via the allInboundRoutes GraphQL query.

        Returns one dict per inbound route. Key fields:

          - ``extension`` — the DID being matched
          - ``cidnum`` — caller-ID match (empty = match any caller)
          - ``description`` — operator-facing label
          - ``destinationConnection`` — human-readable destination string;
            FreePBX renders it like ``"Extensions: 1001 Alice Engineering"``
            or ``"Ring Groups: 600 Sales Team"``. The adapter parses the
            type prefix to decide which target FK to populate.
          - behavior flags (privacyman, alertinfo, ringing, mohclass, etc.)
        """
        gql = """
        query {
          allInboundRoutes {
            totalCount
            inboundRoutes {
              id extension cidnum description destinationConnection
              privacyman alertinfo ringing mohclass grppre delay_answer
              pricid pmmaxretries pmminlength reversal rvolume fanswer
            }
          }
        }
        """
        data = self.query(gql)
        wrapper = data.get("allInboundRoutes") or {}
        return wrapper.get("inboundRoutes") or []

    def list_voicemail_boxes(self, extension_ids: list[str]) -> dict[str, dict]:
        """Fetch voicemail-box config for each extension that has one.

        FreePBX 17's GraphQL has no bulk fetch — we must call
        ``fetchVoiceMail`` per-extension. Returns ``{ext_id: vm_dict}``
        only for extensions whose voicemail is actually enabled
        (detected via ``context != null`` — disabled boxes return all
        nulls). Token caching keeps the per-call overhead small.

        For 1000+ extension deployments this can take 30-60 seconds.
        Consider gating behind an ``enrich_voicemail`` Job toggle the
        way the CCM adapter does ``enrich_phone_lines``. Currently
        always-on; revisit if it becomes a bottleneck.
        """
        boxes: dict[str, dict] = {}
        # Note: arg type is `ID!` not `String!` despite the introspection
        # probe reporting `String` for the field args list. Discovered at
        # runtime — GraphQL servers are allowed to coerce ID↔String for
        # field args but not for query variables.
        gql = (
            "query($ext: ID!) { fetchVoiceMail(extensionId: $ext) "
            "{ context name email pager attach saycid envelope delete } }"
        )
        for ext_id in extension_ids:
            try:
                data = self.query(gql, {"ext": ext_id})
            except FreePBXAPIError:
                continue
            vm = data.get("fetchVoiceMail") or {}
            if vm.get("context"):  # null context = VM not configured for this ext
                boxes[ext_id] = vm
        return boxes

    def list_trunks(self) -> list[dict]:
        """Fetch all trunks via direct MariaDB query.

        FreePBX 17's `api` module 17.0.6 doesn't expose trunks in its
        GraphQL schema, but the data lives in the well-known `trunks`
        table that's been stable since FreePBX 13. Read-only SELECT —
        the adapter never writes through this connection.

        Returns one dict per trunk with: trunkid, tech (sip/pjsip/iax2/
        dahdi), name, outcid, disabled (bool), provider, channelid.
        """
        if not self.db_host:
            return []
        with self._db_cursor() as cur:
            cur.execute(
                "SELECT trunkid, tech, channelid, name, outcid, "
                "       (CASE WHEN disabled = 'on' THEN 1 ELSE 0 END) AS disabled, "
                "       provider, maxchans, dialoutprefix "
                "FROM trunks "
                "ORDER BY trunkid"
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def list_outbound_routes(self) -> list[dict]:
        """Fetch all outbound routes + their patterns + trunk-priority list.

        Three-table join: outbound_routes (the route metadata),
        outbound_route_patterns (one row per dial pattern), and
        outbound_route_trunks (the trunk-priority list per route).

        Returned shape (one dict per route):

            {
              "route_id": int,
              "name": str,
              "outcid": str | None,
              "patterns": [{"prefix": str, "match": str, "prepend": str}, ...],
              "trunk_seq": [(seq, trunk_id), ...],   # ordered by seq asc
            }
        """
        if not self.db_host:
            return []
        with self._db_cursor() as cur:
            # Routes
            cur.execute(
                "SELECT route_id, name, outcid, emergency_route, intracompany_route "
                "FROM outbound_routes ORDER BY route_id"
            )
            cols = [c[0] for c in cur.description]
            routes = [dict(zip(cols, row)) for row in cur.fetchall()]

            # Patterns for all routes — single query, group in Python
            cur.execute(
                "SELECT route_id, match_pattern_prefix AS prefix, "
                "       match_pattern_pass AS match_pattern, "
                "       prepend_digits AS prepend "
                "FROM outbound_route_patterns ORDER BY route_id, match_pattern_prefix"
            )
            patcols = [c[0] for c in cur.description]
            patterns_by_route: dict[int, list[dict]] = {}
            for row in cur.fetchall():
                pat = dict(zip(patcols, row))
                patterns_by_route.setdefault(pat["route_id"], []).append(pat)

            # Trunk priority list per route
            cur.execute(
                "SELECT route_id, trunk_id, seq FROM outbound_route_trunks "
                "ORDER BY route_id, seq"
            )
            tcols = [c[0] for c in cur.description]
            trunks_by_route: dict[int, list[tuple[int, int]]] = {}
            for row in cur.fetchall():
                d = dict(zip(tcols, row))
                trunks_by_route.setdefault(d["route_id"], []).append((d["seq"], d["trunk_id"]))

        for r in routes:
            r["patterns"] = patterns_by_route.get(r["route_id"], [])
            r["trunk_seq"] = trunks_by_route.get(r["route_id"], [])
        return routes

    @contextmanager
    def _db_cursor(self) -> Iterator[Any]:
        """Yield a SELECT-only DB cursor. Lazy-imports pymysql.

        We don't make pymysql a hard dependency of the package since the
        GraphQL-only path is the recommended production pattern. The DB
        path is for resources FreePBX hasn't exposed via API yet.
        """
        try:
            import pymysql
        except ImportError as e:
            raise RuntimeError(
                "FreePBX trunk/route loading requires the `pymysql` package — "
                "add it to your environment to enable DB-direct loading, "
                "or wait for FreePBX to expose these resources via GraphQL."
            ) from e
        conn = pymysql.connect(
            host=self.db_host, port=self.db_port,
            user=self.db_user, password=self.db_password,
            database=self.db_name, charset="utf8mb4",
        )
        try:
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()
        finally:
            conn.close()


def _safe_get(d: dict, *keys: str) -> Any:
    """Return the first non-None value at any of the given keys.

    Defends against schema drift where FreePBX patch releases rename
    GraphQL root fields (``allFoo`` vs ``foo`` vs ``fetchAllFoo``).
    """
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None
