/*
 * Dial-plan trace form — tab toggle + endpoint Select2 autocomplete.
 *
 * Vanilla JS for the tab switch (no jQuery needed); Select2 for the
 * endpoint autocomplete because Nautobot bundles it for its
 * DynamicModelChoiceField widget — we just reuse what's already loaded.
 *
 * Form modes:
 *   - "endpoint": single autocomplete; manual fieldset is hidden &
 *     not validated. Form's `clean()` derives phone_system + CSS.
 *   - "manual":   classic phone_system + CSS picker. Endpoint field
 *     is hidden & not submitted.
 *
 * The active mode lives in a hidden `mode` input that the server
 * inspects to dispatch validation. Initial mode is chosen by:
 *   1. POST/initial value of `mode` (sticky after submit/error)
 *   2. presence of `endpoint` value → "endpoint"
 *   3. presence of `phone_system` or `starting_css` value → "manual"
 *   4. default → "endpoint" (faster path for new traces)
 */
(function () {
  "use strict";

  const form = document.getElementById("dpt-form");
  if (!form) return;

  const modeInput = form.querySelector('input[name="mode"]');
  const tabs = form.querySelectorAll(".dpt-tab-btn");
  const panes = form.querySelectorAll(".dpt-pane");
  const endpointSelect = form.querySelector(".dpt-endpoint-select");

  function setMode(mode) {
    if (modeInput) modeInput.value = mode;
    tabs.forEach((btn) => {
      const isActive = btn.dataset.dptMode === mode;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", isActive ? "true" : "false");
    });
    panes.forEach((pane) => {
      pane.style.display = pane.dataset.dptPane === mode ? "" : "none";
      // Disable inputs in the inactive pane so they aren't submitted /
      // don't trigger HTML5 validation (we use server-side validation).
      pane.querySelectorAll("input, select, textarea").forEach((el) => {
        el.disabled = pane.dataset.dptPane !== mode;
      });
    });
  }

  // Initial mode resolution.
  function pickInitialMode() {
    const initial = modeInput ? modeInput.value : "";
    if (initial === "endpoint" || initial === "manual") return initial;
    if (endpointSelect && endpointSelect.value) return "endpoint";
    const ps = form.querySelector('[name="phone_system"]');
    const css = form.querySelector('[name="starting_css"]');
    if ((ps && ps.value) || (css && css.value)) return "manual";
    return "endpoint";
  }

  setMode(pickInitialMode());

  tabs.forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.dptMode));
  });

  // Endpoint Select2 — Nautobot ships Select2 + jQuery globally.
  if (endpointSelect && window.jQuery && window.jQuery.fn.select2) {
    const $ = window.jQuery;
    const searchUrl = endpointSelect.dataset.searchUrl;
    $(endpointSelect).select2({
      placeholder: "Search phones, DNs, or trunks…",
      allowClear: true,
      // 2 chars before AJAX fires — matches the server's min query length.
      minimumInputLength: 2,
      ajax: {
        url: searchUrl,
        dataType: "json",
        delay: 200,
        data: (params) => ({ q: params.term || "" }),
        processResults: (data) => ({
          results: (data.results || []).map((r) => ({
            id: r.id,
            text: r.text,
            disabled: !!r.disabled,
            // Squirrel away the derived fields for the form to use.
            // Select2 preserves these on the selected <option>'s data.
            phone_system_id: r.phone_system_id,
            phone_system_name: r.phone_system_name,
            starting_css_id: r.starting_css_id,
            starting_css_name: r.starting_css_name,
            kind: r.kind,
          })),
        }),
      },
      // The default sanitiser strips the emoji prefix; keep it.
      escapeMarkup: (m) => m,
    });

    // Mirror the selected label into the hidden endpoint_label field
    // so the result page can render the provenance banner without
    // another DB lookup.
    $(endpointSelect).on("select2:select", (e) => {
      const labelInput = form.querySelector('input[name="endpoint_label"]');
      if (labelInput) {
        labelInput.value = e.params.data.text || "";
      }
      maybePopulateCallingFromDN(e.params.data);
    });
    // When the endpoint is cleared, reset calling_from back to free text.
    $(endpointSelect).on("select2:clear", () => resetCallingFromToText());
  }

  // -----------------------------------------------------------------
  // calling_from DN dropdown — populated when a phone endpoint is picked
  // -----------------------------------------------------------------
  //
  // The template renders TWO widgets sharing name="calling_from":
  //   * <select id="calling-from-dn">  — DN list (initially hidden+disabled)
  //   * <input  name="calling_from">   — free-text fallback (always there)
  // The browser only submits enabled fields, so toggling disabled+display
  // is sufficient — no JS form-data manipulation needed.

  const callingFromDN = form.querySelector('.dpt-calling-from-dn');
  const callingFromInput = form.querySelector(
    'input[name="calling_from"][type="text"], input[name="calling_from"]:not([type])'
  );

  function resetCallingFromToText() {
    if (callingFromDN) {
      callingFromDN.style.display = 'none';
      callingFromDN.disabled = true;
      callingFromDN.innerHTML = '<option value="">— pick a line —</option>';
    }
    if (callingFromInput) {
      callingFromInput.style.display = '';
      callingFromInput.disabled = false;
    }
  }

  function maybePopulateCallingFromDN(endpointData) {
    // Endpoint kinds that point at a phone: "phone" (direct phone hit)
    // and "dn_via_phone" (DN search that resolved to a specific holder
    // phone). Both have id="phone:<uuid>". Trunks + orphan DNs fall back
    // to free text.
    if (!callingFromDN) return;
    if (!endpointData || !endpointData.id) {
      resetCallingFromToText();
      return;
    }
    const id = String(endpointData.id);
    if (!id.startsWith('phone:')) {
      resetCallingFromToText();
      return;
    }
    const phoneId = id.slice('phone:'.length);
    const url = callingFromDN.dataset.linesUrl;
    fetch(`${url}?phone=${encodeURIComponent(phoneId)}`, {
      credentials: 'same-origin',
      headers: {'Accept': 'application/json'},
    })
      .then((r) => r.ok ? r.json() : {lines: []})
      .then((data) => {
        const lines = (data && data.lines) || [];
        if (!lines.length) {
          // No lines — keep the free-text input visible. Operator can
          // still type something.
          resetCallingFromToText();
          return;
        }
        // Replace dropdown contents.
        const opts = ['<option value="">— pick a line —</option>'];
        lines.forEach((ln) => {
          const partLabel = ln.partition ? ` (${ln.partition})` : '';
          const labelTail = ln.label ? ` — ${ln.label}` : '';
          opts.push(
            `<option value="${esc(ln.extension)}">` +
            `Line ${ln.button_index}: ${esc(ln.extension)}${esc(partLabel)}${esc(labelTail)}` +
            `</option>`
          );
        });
        callingFromDN.innerHTML = opts.join('');
        callingFromDN.style.display = '';
        callingFromDN.disabled = false;
        // Hide the text input (still in the DOM but disabled so it
        // doesn't submit; the dropdown wins).
        if (callingFromInput) {
          callingFromInput.style.display = 'none';
          callingFromInput.disabled = true;
          callingFromInput.value = '';
        }
      })
      .catch(() => resetCallingFromToText());
  }

  // Minimal HTML-escape — Select2 itself ignores attributes, but we're
  // injecting strings into option labels here.
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])
    );
  }
})();
