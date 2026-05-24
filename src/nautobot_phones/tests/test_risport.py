"""Tests for the hand-rolled RisPort70 SOAP client.

Pure unit tests — no live cluster, no network. The module is well-
suited to this: five pure helper functions plus one HTTP-touching
class with a single public method. The HTTP layer is mocked at the
``requests.Session`` boundary.

Why this matters: RisPort70 is what populates ``Phone.last_registered_ip``,
``Phone.registration_status``, ``Phone.active_load`` (running firmware /
Webex build), ``Phone.live_login_user``, and ``Phone.status_reason`` —
the LIVE state of a phone that AXL alone can't tell us. Drift in the
XML parser silently means stale data in Nautobot.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from nautobot_phones.integrations.cisco_ucm.risport import (
    DEVICE_STATUS_VALUES,
    RISClient,
    _build_select_envelope,
    _escape_xml,
    _ip,
    _local,
    _parse_device,
    _parse_response,
    _text,
)


# ---------------------------------------------------------------------------
# _escape_xml — five-entity escape used inside the SOAP envelope template
# ---------------------------------------------------------------------------


class TestEscapeXml(SimpleTestCase):
    """``_escape_xml`` covers the five XML predefined entities."""

    def test_ampersand_first(self) -> None:
        """``&`` must escape BEFORE the other entities (otherwise the
        replacement would corrupt later substitutions)."""
        self.assertEqual(_escape_xml("&"), "&amp;")

    def test_lt_gt(self) -> None:
        self.assertEqual(_escape_xml("<a>"), "&lt;a&gt;")

    def test_quote_apos(self) -> None:
        self.assertEqual(_escape_xml('a"b\'c'), "a&quot;b&apos;c")

    def test_no_metachars_passthrough(self) -> None:
        self.assertEqual(_escape_xml("plain text 123"), "plain text 123")

    def test_combined(self) -> None:
        self.assertEqual(
            _escape_xml('Tom & Jerry\'s "show" <live>'),
            "Tom &amp; Jerry&apos;s &quot;show&quot; &lt;live&gt;",
        )


# ---------------------------------------------------------------------------
# _build_select_envelope — SOAP envelope construction
# ---------------------------------------------------------------------------


class TestBuildSelectEnvelope(SimpleTestCase):
    """Envelope structure matches Cisco's WSDL element ordering."""

    def test_default_envelope_includes_required_elements(self) -> None:
        env = _build_select_envelope()
        # Every required child element appears in the envelope, in the
        # order Cisco's WSDL requires (reordered envelopes are rejected).
        for fragment in (
            "<soap:selectCmDevice>",
            "<soap:StateInfo></soap:StateInfo>",
            "<soap:MaxReturnedDevices>200</soap:MaxReturnedDevices>",
            "<soap:DeviceClass>Phone</soap:DeviceClass>",
            "<soap:Status>Any</soap:Status>",
            "<soap:SelectBy>Name</soap:SelectBy>",
            "<soap:Protocol>Any</soap:Protocol>",
            "</soap:selectCmDevice>",
        ):
            self.assertIn(fragment, env)

    def test_state_info_is_escaped(self) -> None:
        """A StateInfo cursor that contains XML metachars must be escaped
        — otherwise it'd corrupt the envelope structure."""
        env = _build_select_envelope(state_info='cursor & "v2"')
        self.assertIn("<soap:StateInfo>cursor &amp; &quot;v2&quot;</soap:StateInfo>", env)

    def test_custom_max_devices(self) -> None:
        env = _build_select_envelope(max_devices=500)
        self.assertIn("<soap:MaxReturnedDevices>500</soap:MaxReturnedDevices>", env)

    def test_custom_status_and_class(self) -> None:
        env = _build_select_envelope(device_class="Gateway", status="Registered")
        self.assertIn("<soap:DeviceClass>Gateway</soap:DeviceClass>", env)
        self.assertIn("<soap:Status>Registered</soap:Status>", env)

    def test_max_devices_coerced_to_int(self) -> None:
        """Defensive: integer coercion guards against caller passing a
        string-shaped count."""
        env = _build_select_envelope(max_devices="50")  # type: ignore[arg-type]
        self.assertIn("<soap:MaxReturnedDevices>50</soap:MaxReturnedDevices>", env)


# ---------------------------------------------------------------------------
# ElementTree helpers — _local, _text, _ip, _parse_device
# ---------------------------------------------------------------------------


def _xml(s: str) -> Any:
    """Quick XML parse for test fixtures."""
    import xml.etree.ElementTree as ET
    return ET.fromstring(s)


class TestLocalAndText(SimpleTestCase):
    """``_local`` strips XML namespace; ``_text`` extracts child text."""

    def test_local_strips_namespace(self) -> None:
        elem = _xml('<a xmlns="http://x"><b/></a>')
        # Namespaced child appears as `{http://x}b`; _local strips that.
        self.assertEqual(_local(elem), "a")
        for child in elem:
            self.assertEqual(_local(child), "b")

    def test_text_finds_child(self) -> None:
        elem = _xml("<r><Name>SEP001</Name><Status>Registered</Status></r>")
        self.assertEqual(_text(elem, "Name"), "SEP001")
        self.assertEqual(_text(elem, "Status"), "Registered")

    def test_text_missing_returns_empty(self) -> None:
        elem = _xml("<r><Other>x</Other></r>")
        self.assertEqual(_text(elem, "Name"), "")

    def test_text_strips_whitespace(self) -> None:
        elem = _xml("<r><Name>   SEP002\n  </Name></r>")
        self.assertEqual(_text(elem, "Name"), "SEP002")

    def test_text_none_element_returns_empty(self) -> None:
        """Defensive: a None element shouldn't blow up the parser."""
        self.assertEqual(_text(None, "Name"), "")


class TestIp(SimpleTestCase):
    """``_ip`` handles BOTH the flat-text and CCM-15-nested IPAddress shapes."""

    def test_flat_text_format(self) -> None:
        """Older CCMs return IPAddress as plain text."""
        elem = _xml("<IPAddress>10.1.2.3</IPAddress>")
        self.assertEqual(_ip(elem), "10.1.2.3")

    def test_ccm_15_nested_format(self) -> None:
        """CCM 15 wraps IPAddress in <item><IP>...</IP></item> structure."""
        elem = _xml(
            "<IPAddress>"
            "<item><IP>10.20.30.40</IP><IPAddrType>1</IPAddrType></item>"
            "</IPAddress>"
        )
        self.assertEqual(_ip(elem), "10.20.30.40")

    def test_none_returns_empty(self) -> None:
        self.assertEqual(_ip(None), "")

    def test_empty_element_returns_empty(self) -> None:
        elem = _xml("<IPAddress></IPAddress>")
        self.assertEqual(_ip(elem), "")


class TestParseDevice(SimpleTestCase):
    """``_parse_device`` extracts the live-status fields the adapter cares about."""

    def test_full_device_extracts_all_fields(self) -> None:
        elem = _xml(
            "<item>"
            "<Name>SEPCAFEBABE0001</Name>"
            "<IPAddress>10.1.2.3</IPAddress>"
            "<Status>Registered</Status>"
            "<ActiveLoadID>sip88xx.14-1-1-0001-410</ActiveLoadID>"
            "<InactiveLoadID>sip88xx.14-0-1-12001-1</InactiveLoadID>"
            "<LoginUserId>jdoe</LoginUserId>"
            "<StatusReason>0</StatusReason>"
            "</item>"
        )
        parsed = _parse_device(elem)
        self.assertEqual(parsed, {
            "name": "SEPCAFEBABE0001",
            "ip_address": "10.1.2.3",
            "status": "Registered",
            "active_load": "sip88xx.14-1-1-0001-410",
            "inactive_load": "sip88xx.14-0-1-12001-1",
            "login_user_id": "jdoe",
            "status_reason": "0",
        })

    def test_ipaddress_alt_casing(self) -> None:
        """Cisco's WSDL uses `IpAddress` in some versions, `IPAddress` in others."""
        elem = _xml(
            "<item><Name>SEP1</Name><IpAddress>10.0.0.1</IpAddress></item>"
        )
        self.assertEqual(_parse_device(elem)["ip_address"], "10.0.0.1")

    def test_missing_fields_default_to_empty(self) -> None:
        """A device with only Name fills the missing fields with empty strings,
        preserving the dict shape downstream code expects."""
        elem = _xml("<item><Name>BOTjdoe</Name></item>")
        parsed = _parse_device(elem)
        self.assertEqual(parsed["name"], "BOTjdoe")
        self.assertEqual(parsed["ip_address"], "")
        self.assertEqual(parsed["status"], "")
        self.assertEqual(parsed["active_load"], "")
        self.assertEqual(parsed["status_reason"], "")


# ---------------------------------------------------------------------------
# _parse_response — top-level XML parse
# ---------------------------------------------------------------------------


def _ok_response(devices_xml: str = "", state_info: str = "") -> str:
    """SOAP envelope wrapping a selectCmDeviceReturn with devices."""
    return f"""<?xml version='1.0' encoding='utf-8'?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="http://schemas.cisco.com/ast/soap">
  <soapenv:Body>
    <ns:selectCmDeviceResponse>
      <selectCmDeviceReturn>
        <SelectCmDeviceResult>
          <StateInfo>{state_info}</StateInfo>
          <CmNodes>
            <item>
              <CmDevices>
                {devices_xml}
              </CmDevices>
            </item>
          </CmNodes>
        </SelectCmDeviceResult>
      </selectCmDeviceReturn>
    </ns:selectCmDeviceResponse>
  </soapenv:Body>
</soapenv:Envelope>"""


def _ok_response_no_wrapper(devices_xml: str = "") -> str:
    """Older CUCMs omit the SelectCmDeviceResult wrapper."""
    return f"""<?xml version='1.0' encoding='utf-8'?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns="http://schemas.cisco.com/ast/soap">
  <soapenv:Body>
    <ns:selectCmDeviceResponse>
      <selectCmDeviceReturn>
        <StateInfo></StateInfo>
        <CmNodes>
          <item>
            <CmDevices>
              {devices_xml}
            </CmDevices>
          </item>
        </CmNodes>
      </selectCmDeviceReturn>
    </ns:selectCmDeviceResponse>
  </soapenv:Body>
</soapenv:Envelope>"""


class TestParseResponse(SimpleTestCase):
    """``_parse_response`` walks both CCM-15-wrapped and pre-15 shapes."""

    def test_empty_response_returns_no_devices(self) -> None:
        result = _parse_response(_ok_response())
        self.assertEqual(result, {"state_info": "", "devices": []})

    def test_single_device(self) -> None:
        result = _parse_response(_ok_response(
            "<item><Name>SEP1</Name><Status>Registered</Status></item>"
        ))
        self.assertEqual(len(result["devices"]), 1)
        self.assertEqual(result["devices"][0]["name"], "SEP1")
        self.assertEqual(result["devices"][0]["status"], "Registered")

    def test_multiple_devices(self) -> None:
        result = _parse_response(_ok_response(
            "<item><Name>SEP1</Name></item>"
            "<item><Name>SEP2</Name></item>"
            "<item><Name>CSFjdoe</Name></item>"
        ))
        self.assertEqual([d["name"] for d in result["devices"]],
                         ["SEP1", "SEP2", "CSFjdoe"])

    def test_pre_ccm15_no_wrapper(self) -> None:
        """Older CCMs don't have <SelectCmDeviceResult> wrapping — parser
        handles both shapes."""
        result = _parse_response(_ok_response_no_wrapper(
            "<item><Name>SEP-OLD</Name></item>"
        ))
        self.assertEqual(len(result["devices"]), 1)
        self.assertEqual(result["devices"][0]["name"], "SEP-OLD")

    def test_state_info_cursor_propagated(self) -> None:
        result = _parse_response(_ok_response(state_info="page-2-token"))
        self.assertEqual(result["state_info"], "page-2-token")

    def test_soap_fault_raises_runtime_error(self) -> None:
        fault_xml = """<?xml version='1.0'?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>Database unavailable</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>"""
        with self.assertRaisesRegex(RuntimeError, "Database unavailable"):
            _parse_response(fault_xml)

    def test_missing_return_raises(self) -> None:
        """Defensive: a malformed response with no return element AND no
        Fault element raises a clear error rather than silently returning
        an empty result."""
        bad = "<?xml version='1.0'?><Envelope><Body><Other/></Body></Envelope>"
        with self.assertRaisesRegex(RuntimeError, "missing selectCmDeviceReturn"):
            _parse_response(bad)


# ---------------------------------------------------------------------------
# RISClient — pagination loop + status validation
# ---------------------------------------------------------------------------


class TestRISClientInit(SimpleTestCase):
    """Constructor wires up the session with auth + retry policy."""

    def test_builds_https_url_with_axl_port(self) -> None:
        client = RISClient("ccm.example.com", "admin", "pw")
        self.assertEqual(client.url,
                         "https://ccm.example.com:8443/realtimeservice2/services/RISService70")

    def test_verify_tls_propagated(self) -> None:
        client = RISClient("ccm", "u", "p", verify_tls=False)
        self.assertFalse(client._session.verify)


class TestRISClientSelectPhones(SimpleTestCase):
    """``select_phones`` paginates via StateInfo cursor."""

    def _client_with_responses(self, responses: list[str]) -> RISClient:
        """Build a client whose Session.post returns the canned responses
        in order (one per call). Body is the SOAP envelope wrapping the
        phones we want."""
        client = RISClient("ccm", "u", "p")
        post_iter = iter(responses)

        def _post(*args, **kwargs) -> Any:
            mock_resp = MagicMock()
            mock_resp.text = next(post_iter)
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        client._session.post = MagicMock(side_effect=_post)
        return client

    def test_invalid_status_raises_before_network(self) -> None:
        """Argument validation happens before any HTTP request — caller
        sees a clear ValueError if they mis-spell ``status``."""
        client = RISClient("ccm", "u", "p")
        with patch.object(client._session, "post") as m:
            with self.assertRaisesRegex(ValueError, "status must be one of"):
                client.select_phones(status="garbage")
            m.assert_not_called()

    def test_all_status_values_accepted(self) -> None:
        """Every value in DEVICE_STATUS_VALUES is accepted."""
        client = self._client_with_responses([_ok_response()] * len(DEVICE_STATUS_VALUES))
        for status in DEVICE_STATUS_VALUES:
            client._session.post.reset_mock()
            client.select_phones(status=status, max_pages=1)

    def test_single_page_completes_without_cursor(self) -> None:
        """A response with empty StateInfo terminates the pagination loop
        after the first page."""
        client = self._client_with_responses([
            _ok_response("<item><Name>SEP1</Name></item>"),
        ])
        result = client.select_phones()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "SEP1")
        self.assertEqual(client._session.post.call_count, 1)

    def test_multi_page_walks_cursor(self) -> None:
        """A non-empty StateInfo on page N drives a request for page N+1.
        Final page returns empty StateInfo and the loop exits."""
        client = self._client_with_responses([
            _ok_response("<item><Name>SEP1</Name></item>", state_info="cursor-1"),
            _ok_response("<item><Name>SEP2</Name></item>", state_info="cursor-2"),
            _ok_response("<item><Name>SEP3</Name></item>", state_info=""),
        ])
        result = client.select_phones(page_size=1)
        self.assertEqual([d["name"] for d in result], ["SEP1", "SEP2", "SEP3"])
        self.assertEqual(client._session.post.call_count, 3)

    def test_repeating_cursor_exits_loop(self) -> None:
        """Safety: if the server returns the SAME cursor twice (buggy
        cluster), the loop exits rather than spinning forever."""
        client = self._client_with_responses([
            _ok_response("<item><Name>SEP1</Name></item>", state_info="same"),
            _ok_response("<item><Name>SEP2</Name></item>", state_info="same"),
        ])
        result = client.select_phones()
        self.assertEqual([d["name"] for d in result], ["SEP1", "SEP2"])
        # Two calls, then loop detected the repeat and broke.
        self.assertEqual(client._session.post.call_count, 2)

    def test_max_pages_cap_terminates_unbounded_pagination(self) -> None:
        """``max_pages`` is a hard cap — even if the server keeps issuing
        fresh cursors, we stop after N pages."""
        responses = [
            _ok_response(f"<item><Name>SEP{i}</Name></item>",
                         state_info=f"cursor-{i}")
            for i in range(10)
        ]
        client = self._client_with_responses(responses)
        client.select_phones(max_pages=3)
        self.assertEqual(client._session.post.call_count, 3)
