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
    });
  }
})();
