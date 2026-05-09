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
mapping FreePBX records into our DiffSync models.

Parameters:
    base_url: Origin URL of the FreePBX admin (no trailing slash).
        Example: ``"http://freepbx"`` (Docker DNS) or ``"https://pbx.example.com"``.
    client_id: OAuth2 application client_id (from FreePBX Admin > API > Applications).
    client_secret: OAuth2 application client_secret.
    verify_tls: Verify the FreePBX TLS cert. Default True; disable for
        self-signed dev installs (the dev container uses HTTP anyway).
    timeout: Per-request timeout in seconds.

Raises:
    FreePBXAuthError: Token acquisition failed (bad credentials / scopes).
    FreePBXAPIError: GraphQL endpoint returned an error response.
"""

from __future__ import annotations

import time
from typing import Any, Optional

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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._http = httpx.Client(verify=verify_tls, timeout=timeout)
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

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

    def list_trunks(self) -> list[dict]:
        """Fetch all trunks.

        STUB — trunks aren't exposed via the api module's default schema in
        17.0.6; they require the `outroutes`/`trunks` API extensions which
        ship as separate modules. Stage-5 work.
        """
        return []

    def list_outbound_routes(self) -> list[dict]:
        """Fetch all outbound routes.

        STUB — see ``list_trunks`` note. Stage-5 work.
        """
        return []


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
