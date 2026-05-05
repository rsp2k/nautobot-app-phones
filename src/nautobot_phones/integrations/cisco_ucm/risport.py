"""RisPort70 — real-time device registration status from CUCM.

Complementary to AXL: AXL tells us what's *configured*; RisPort tells us
what's *currently happening* — registration state, IP address, last
registered timestamp. For our mirror flow, RisPort is the source of
truth for `Phone.last_registered_ip` and live `Phone.registration_status`.

RisPort lives at `/realtimeservice2/services/RISService70` on the same
host as AXL. Unlike AXL it doesn't go through zeep — Cisco's RIS WSDL
has fragile cross-imports and it's substantially easier to hand-roll
the small set of SOAP envelopes we need. Pattern adapted from the
mcaxl project.

Auto-paginates via the `StateInfo` cursor for clusters with more than
`page_size` devices (default 200). Single-cluster CUCMs typically need
5-10 pages for a full phone inventory.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from requests import Session
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry


_RIS_PATH = "/realtimeservice2/services/RISService70"
_NS_SOAPENV = "http://schemas.xmlsoap.org/soap/envelope/"
_NS_RIS = "http://schemas.cisco.com/ast/soap"

DEVICE_STATUS_VALUES = (
    "Any", "Registered", "UnRegistered", "Rejected",
    "PartiallyRegistered", "Unknown",
)


def _escape_xml(s: str) -> str:
    """Minimal XML entity escape for values injected into SOAP envelopes."""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&apos;")
    )


def _build_select_envelope(
    state_info: str = "",
    max_devices: int = 200,
    device_class: str = "Phone",
    status: str = "Any",
) -> str:
    """Build a `selectCmDevice` SOAP envelope.

    The CmSelectionCriteria child elements must appear in the exact order
    Cisco's WSDL expects (re-ordered envelopes are rejected). Always
    include every field with sensible defaults.
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soapenv:Envelope xmlns:soapenv="{_NS_SOAPENV}" xmlns:soap="{_NS_RIS}">'
        "<soapenv:Header/>"
        "<soapenv:Body>"
        "<soap:selectCmDevice>"
        f"<soap:StateInfo>{_escape_xml(state_info)}</soap:StateInfo>"
        "<soap:CmSelectionCriteria>"
        f"<soap:MaxReturnedDevices>{int(max_devices)}</soap:MaxReturnedDevices>"
        f"<soap:DeviceClass>{_escape_xml(device_class)}</soap:DeviceClass>"
        "<soap:Model>255</soap:Model>"
        f"<soap:Status>{_escape_xml(status)}</soap:Status>"
        "<soap:NodeName></soap:NodeName>"
        "<soap:SelectBy>Name</soap:SelectBy>"
        "<soap:SelectItems><soap:item><soap:Item>*</soap:Item></soap:item></soap:SelectItems>"
        "<soap:Protocol>Any</soap:Protocol>"
        "<soap:DownloadStatus>Any</soap:DownloadStatus>"
        "</soap:CmSelectionCriteria>"
        "</soap:selectCmDevice>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )


def _local(elem: ET.Element) -> str:
    return elem.tag.split("}")[-1]


def _text(elem: Optional[ET.Element], tag: str) -> str:
    if elem is None:
        return ""
    for child in elem:
        if _local(child) == tag:
            return (child.text or "").strip()
    return ""


def _ip(elem: Optional[ET.Element]) -> str:
    """CUCM 15 returns IPAddress as nested struct; older versions are flat."""
    if elem is None:
        return ""
    if elem.text and elem.text.strip():
        return elem.text.strip()
    for item_elem in elem:
        if _local(item_elem).lower() == "item":
            for ip_elem in item_elem:
                if _local(ip_elem) == "IP":
                    return (ip_elem.text or "").strip()
    return ""


def _parse_device(elem: ET.Element) -> dict:
    """Extract per-device fields from a RisPort `<item>` element.

    Returns a flat dict so caller can index by device name. The expensive
    fields are the live-status set: ActiveLoadID gives us the running
    Webex/Jabber/firmware build, InactiveLoadID is the rollback target,
    LoginUserId tells us who's signed in right now (vs AXL's configured
    owner), and StatusReason explains why a phone is in its current
    registration state.
    """
    ip_elem = None
    for child in elem:
        if _local(child) in ("IPAddress", "IpAddress"):
            ip_elem = child
            break
    return {
        "name": _text(elem, "Name"),
        "ip_address": _ip(ip_elem),
        "status": _text(elem, "Status"),
        "active_load": _text(elem, "ActiveLoadID"),
        "inactive_load": _text(elem, "InactiveLoadID"),
        "login_user_id": _text(elem, "LoginUserId"),
        "status_reason": _text(elem, "StatusReason"),
    }


def _parse_response(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    select_return: Optional[ET.Element] = None
    for elem in root.iter():
        if _local(elem) == "selectCmDeviceReturn":
            select_return = elem
            break
    if select_return is None:
        for elem in root.iter():
            if _local(elem) == "Fault":
                raise RuntimeError(f"RisPort SOAP fault: {_text(elem, 'faultstring') or 'unknown'}")
        raise RuntimeError("RisPort response missing selectCmDeviceReturn")
    # CUCM 15 wraps in <SelectCmDeviceResult>; older versions don't.
    for child in select_return:
        if _local(child) == "SelectCmDeviceResult":
            select_return = child
            break
    state_info = _text(select_return, "StateInfo")
    devices: list[dict] = []
    for child in select_return:
        if _local(child) == "CmNodes":
            for node_elem in child:
                if _local(node_elem) != "item":
                    continue
                for cm_devices in node_elem:
                    if _local(cm_devices) != "CmDevices":
                        continue
                    for dev_item in cm_devices:
                        if _local(dev_item) == "item":
                            devices.append(_parse_device(dev_item))
    return {"state_info": state_info, "devices": devices}


class RISClient:
    """Real-time Information Server client for CUCM phone status.

    Hand-rolled SOAP — no WSDL parsing. Reuses the AXL endpoint's host
    + credentials. Read-only by design — only invokes `selectCmDevice`.
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        verify_tls: bool = True,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.url = f"https://{host}:8443{_RIS_PATH}"
        self.timeout = timeout

        session = Session()
        session.verify = verify_tls
        session.auth = HTTPBasicAuth(username, password)
        retry = Retry(
            total=3, backoff_factor=1.0,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset(["POST"]),
            raise_on_status=False,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session = session

    def select_phones(
        self,
        status: str = "Any",
        page_size: int = 200,
        max_pages: int = 20,
    ) -> list[dict]:
        """Walk all phones, auto-paginating via StateInfo cursor.

        Returns flat list of {"name", "ip_address", "status"} dicts.
        """
        if status not in DEVICE_STATUS_VALUES:
            raise ValueError(f"status must be one of {DEVICE_STATUS_VALUES}; got {status!r}")
        all_devices: list[dict] = []
        state_info = ""
        for _ in range(max_pages):
            envelope = _build_select_envelope(
                state_info=state_info,
                max_devices=page_size,
                device_class="Phone",
                status=status,
            )
            resp = self._session.post(
                self.url,
                data=envelope,
                headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '"selectCmDevice"'},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            page = _parse_response(resp.text)
            all_devices.extend(page["devices"])
            next_cursor = page.get("state_info") or ""
            if not next_cursor or next_cursor == state_info:
                break
            state_info = next_cursor
        return all_devices
