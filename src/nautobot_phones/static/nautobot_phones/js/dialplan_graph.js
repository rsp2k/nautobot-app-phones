/*
 * Dial-plan graph — interactive Cytoscape view of CSS → patterns →
 * destinations (forward) or trunk → patterns → CSSes (backward).
 *
 * Layout: dagre (hierarchical, left-to-right). The dial plan is
 * naturally tiered, so a layered layout reads better than the default
 * force-directed "cose" which produces a snowflake shape.
 *
 * Wiring:
 *   - Anchor picker is a Select2 over /endpoint-search/ (reused from
 *     the trace form). Filters in-app for CSS + Trunk per direction.
 *   - Direction buttons toggle a query param + re-fetch.
 *   - Click a node: surface its detail link in the side info pane.
 *
 * URL state: ?anchor=<kind>:<uuid>&direction=<forward|backward>.
 * Pushed via pushState so refresh + back-button work.
 */
(function () {
  "use strict";

  const root = document.getElementById("dpg-canvas");
  if (!root) return;

  const $ = window.jQuery;
  const cytoscape = window.cytoscape;
  if (cytoscape && window.cytoscapeDagre) {
    cytoscape.use(window.cytoscapeDagre);
  } else if (cytoscape && window.dagre) {
    // cytoscape-dagre registers itself as window.cytoscapeDagre on
    // some bundles, falls through to global cytoscape.use on others.
    // No-op here — the UMD shim handled it.
  }

  const dataUrl = root.dataset.dataUrl;
  const anchorSelect = document.getElementById("dpg-anchor");
  const dirButtons = document.querySelectorAll(".dpg-dir-btn");
  const fitBtn = document.getElementById("dpg-fit");
  const relayoutBtn = document.getElementById("dpg-relayout");
  const infoPane = document.getElementById("dpg-info");
  const infoLabel = infoPane.querySelector(".dpg-info-label");
  const infoKind = infoPane.querySelector(".dpg-info-kind");
  const infoExtras = infoPane.querySelector(".dpg-info-extras");
  const infoLink = document.getElementById("dpg-info-link");
  const dialedInput = document.getElementById("dpg-dialed");
  const tracePane = document.getElementById("dpg-trace");
  const traceList = tracePane ? tracePane.querySelector(".dpg-trace-steps") : null;
  const traceCount = tracePane ? tracePane.querySelector(".dpg-trace-count") : null;

  let state = {
    anchor: root.dataset.initialAnchor || "",
    direction: root.dataset.initialDirection || "forward",
    dialed: (dialedInput && dialedInput.value) || "",
    cy: null,
  };

  // ---- Dial input — debounced, re-fetches the graph with trace overlay ----

  if (dialedInput) {
    let dialedTimer = null;
    dialedInput.addEventListener("input", () => {
      clearTimeout(dialedTimer);
      // 300ms debounce — operators type and pause, we don't want to fire
      // a graph rebuild for every keystroke.
      dialedTimer = setTimeout(() => {
        state.dialed = dialedInput.value.trim();
        reloadGraph();
      }, 300);
    });
  }

  // ---- Anchor autocomplete -----------------------------------------------

  if ($ && $.fn.select2 && anchorSelect) {
    const searchUrl = anchorSelect.dataset.searchUrl;
    $(anchorSelect).select2({
      placeholder: "Search CSS or trunk…",
      allowClear: true,
      minimumInputLength: 2,
      ajax: {
        url: searchUrl,
        dataType: "json",
        delay: 200,
        data: (params) => ({q: params.term || ""}),
        processResults: (data) => ({
          // Filter to the kinds that make sense per direction.
          results: (data.results || [])
            .filter((r) => filterResultForDirection(r))
            .map((r) => ({
              id: r.id,
              text: r.text,
              disabled: !!r.disabled,
              kind: r.kind,
            })),
        }),
      },
      escapeMarkup: (m) => m,
    });
    $(anchorSelect).on("select2:select", (e) => {
      state.anchor = e.params.data.id || "";
      reloadGraph();
    });
    $(anchorSelect).on("select2:clear", () => {
      state.anchor = "";
      reloadGraph();
    });
  }

  function filterResultForDirection(r) {
    // Forward: CSS hits make sense (start of a call). Trunk would be
    // backward-only. DN/phone hits don't have a "start a graph" semantic
    // — they're more "start a trace" things. So forward = CSS only.
    if (state.direction === "forward") {
      return r.id && r.id.startsWith("css:");
    }
    // Backward: walk-back from trunk only.
    return r.id && r.id.startsWith("trunk:");
  }

  // ---- Direction toggle --------------------------------------------------

  dirButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      state.direction = btn.dataset.dpgDir;
      // Visually toggle the buttons.
      dirButtons.forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
      // The anchor type changes with direction — clear the old anchor
      // if it doesn't match the new direction.
      if (state.anchor) {
        const kind = state.anchor.split(":")[0];
        if ((state.direction === "forward" && kind !== "css") ||
            (state.direction === "backward" && kind !== "trunk")) {
          state.anchor = "";
          if ($ && $.fn.select2 && anchorSelect) {
            $(anchorSelect).val(null).trigger("change");
          }
        }
      }
      reloadGraph();
    });
  });
  // Set initial pressed state.
  dirButtons.forEach((b) => {
    b.classList.toggle("active", b.dataset.dpgDir === state.direction);
    b.setAttribute("aria-pressed",
      b.dataset.dpgDir === state.direction ? "true" : "false");
  });

  // ---- Graph load --------------------------------------------------------

  function reloadGraph() {
    pushUrlState();
    if (!state.anchor) {
      renderEmpty("Pick an anchor above to render the graph.");
      return;
    }
    const params = new URLSearchParams({
      anchor: state.anchor,
      direction: state.direction,
    });
    if (state.dialed) params.set("dialed_digits", state.dialed);
    const url = `${dataUrl}?${params.toString()}`;
    fetch(url, {credentials: "same-origin",
                headers: {"Accept": "application/json"}})
      .then((r) => r.ok ? r.json() : Promise.reject(r.statusText))
      .then((data) => render(data))
      .catch((err) => renderEmpty(`Failed to load: ${err}`));
  }

  function renderEmpty(message) {
    if (state.cy) {
      state.cy.destroy();
      state.cy = null;
    }
    root.innerHTML = `<div class="dpg-empty-state">${esc(message)}</div>`;
    infoPane.hidden = true;
  }

  function render(data) {
    if (!data.nodes || data.nodes.length === 0) {
      renderEmpty("No data — anchor may have been deleted, or graph has no reachable elements.");
      return;
    }
    if (state.cy) {
      state.cy.destroy();
      state.cy = null;
    }
    root.innerHTML = "";
    state.cy = cytoscape({
      container: root,
      elements: {
        nodes: data.nodes,
        edges: data.edges,
      },
      style: cytoStyle(),
      minZoom: 0.1,
      maxZoom: 3.0,
    });
    state.cy.on("tap", "node", (evt) => showInfo(evt.target));
    state.cy.on("tap", (evt) => {
      if (evt.target === state.cy) infoPane.hidden = true;
    });
    // Layout is async — fit AFTER it finishes, otherwise we fit on a
    // collapsed/zero-size graph.
    const layout = state.cy.layout(dagreLayout());
    layout.one("layoutstop", () => {
      // Apply trace overlay *after* layout, so the highlighted nodes
      // sit at their final positions when we zoom-fit to them.
      applyTraceOverlay(data.meta);
      state.cy.fit(undefined, 40);
    });
    layout.run();
  }

  function applyTraceOverlay(meta) {
    // No trace = unhighlighted topology; clear any prior trace state.
    if (!meta || !meta.has_trace || !meta.trace_steps) {
      if (tracePane) tracePane.hidden = true;
      // Strip in-trace / dimmed classes (no-op on fresh cy, matters on
      // re-render after dial was set then cleared).
      if (state.cy) {
        state.cy.elements().removeClass("in-trace dimmed trace-step-head trace-step-tail");
      }
      return;
    }
    const cy = state.cy;
    // Mark nodes that appear in the trace.
    cy.nodes('[step_index >= 0]').addClass("in-trace");
    // The head node (step 0) and the terminal step get extra emphasis.
    cy.nodes('[step_index = 0]').addClass("trace-step-head");
    const lastIdx = (meta.trace_steps[meta.trace_steps.length - 1] || {}).index;
    if (typeof lastIdx === "number") {
      cy.nodes(`[step_index = ${lastIdx}]`).addClass("trace-step-tail");
    }
    // Dim everything NOT in the trace so the path pops visually.
    cy.elements().difference(cy.nodes(".in-trace")).addClass("dimmed");
    // Highlight edges connecting consecutive in-trace nodes — operators
    // immediately see "this edge is on the call's path."
    cy.edges().forEach((e) => {
      const s = e.source().data("step_index");
      const t = e.target().data("step_index");
      if (typeof s === "number" && typeof t === "number") {
        e.removeClass("dimmed");
        e.addClass("in-trace");
      }
    });
    renderTracePanel(meta.trace_steps);
  }

  function renderTracePanel(steps) {
    if (!tracePane || !traceList) return;
    tracePane.hidden = false;
    traceCount.textContent = `${steps.length} steps`;
    traceList.innerHTML = "";
    steps.forEach((step) => {
      const li = document.createElement("li");
      li.className = `dpg-trace-step dpg-trace-kind-${step.kind}`;
      li.dataset.nodeId = step.node_id || "";
      const kindLabel = step.kind.replace(/_/g, " ");
      li.innerHTML = `
        <div class="dpg-trace-step-kind">${esc(kindLabel)}</div>
        <div class="dpg-trace-step-summary">${esc(step.summary || "")}</div>
        ${step.subject ? `<code class="dpg-trace-step-subject">${esc(step.subject)}</code>` : ""}
      `;
      if (step.node_id) {
        li.addEventListener("click", () => focusNode(step.node_id));
        li.classList.add("dpg-trace-clickable");
      }
      traceList.appendChild(li);
    });
  }

  function focusNode(nodeId) {
    if (!state.cy) return;
    const node = state.cy.getElementById(nodeId);
    if (!node || !node.length) return;
    state.cy.animate({
      center: {eles: node},
      zoom: Math.max(0.8, state.cy.zoom()),
    }, {duration: 250});
    // Briefly pulse — visual confirmation the step is "here."
    node.flashClass("trace-pulse", 800);
  }

  function dagreLayout() {
    return {
      name: "dagre",
      rankDir: "LR",   // left-to-right hierarchy
      nodeSep: 30,
      rankSep: 70,
      padding: 20,
      animate: false,
    };
  }

  function cytoStyle() {
    return [
      {selector: "node", style: {
        "label": "data(label)",
        "font-size": "11px",
        "font-family": "ui-monospace, SFMono-Regular, Consolas, monospace",
        "color": "#fff",
        "text-outline-color": "#0a0a0a",
        "text-outline-width": 2,
        "text-valign": "center",
        "text-halign": "center",
        "text-wrap": "wrap",
        "text-max-width": "140px",
        "background-color": "#666",
        "border-width": 2,
        "border-color": "#333",
        "shape": "round-rectangle",
        "padding": "8px",
        "width": 140,
        "height": 32,
      }},
      {selector: "node[kind = 'css']", style: {
        "background-color": "#0d6efd",
        "border-color": "#0a4fb8",
        "shape": "round-rectangle",
      }},
      {selector: "node[kind = 'partition']", style: {
        "background-color": "#6c757d",
        "border-color": "#3f464d",
      }},
      {selector: "node[kind = 'pattern']", style: {
        "background-color": "#ffc107",
        "border-color": "#b07e00",
        "color": "#000",
        "text-outline-color": "#fff",
      }},
      {selector: "node[kind = 'translation']", style: {
        "background-color": "#fd7e14",
        "border-color": "#b75710",
        "shape": "diamond",
        "color": "#fff",
      }},
      {selector: "node[kind = 'dn']", style: {
        "background-color": "#198754",
        "border-color": "#0f5132",
      }},
      {selector: "node[kind = 'trunk']", style: {
        "background-color": "#dc3545",
        "border-color": "#971b25",
        "shape": "round-hexagon",
      }},
      {selector: "node[kind = 'route_list']", style: {
        "background-color": "#0dcaf0",
        "border-color": "#066d80",
        "color": "#000",
        "text-outline-color": "#fff",
      }},
      {selector: "node[kind = 'route_group']", style: {
        "background-color": "#20c997",
        "border-color": "#117862",
      }},
      {selector: "node[kind = 'hunt_pilot']", style: {
        "background-color": "#d49b00",
        "border-color": "#7e5d00",
      }},
      {selector: "node[kind = 'hunt_list']", style: {
        "background-color": "#946800",
        "border-color": "#4d3700",
      }},
      {selector: "node[kind = 'analog_gateway']", style: {
        "background-color": "#e83e8c",
        "border-color": "#9c1d5c",
      }},
      {selector: "node[kind = 'collapsed']", style: {
        "background-color": "#343a40",
        "border-color": "#1f2326",
        "border-style": "dashed",
        "shape": "round-rectangle",
        "color": "#aaa",
      }},
      {selector: "edge", style: {
        "width": 2,
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        "line-color": "#6c757d",
        "target-arrow-color": "#6c757d",
        "label": "data(label)",
        "font-size": "9px",
        "color": "#aaa",
        "text-background-color": "#1a1a1a",
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-rotation": "autorotate",
      }},
      {selector: "edge[kind = 'css_priority']", style: {
        "line-color": "#0d6efd",
        "target-arrow-color": "#0d6efd",
      }},
      {selector: "edge[kind = 'rl_priority']", style: {
        "line-color": "#0dcaf0",
        "target-arrow-color": "#0dcaf0",
      }},
      {selector: "edge[kind = 'rg_priority']", style: {
        "line-color": "#20c997",
        "target-arrow-color": "#20c997",
      }},
      {selector: "edge[kind = 'collapsed']", style: {
        "line-style": "dashed",
        "line-color": "#343a40",
        "target-arrow-color": "#343a40",
      }},
      {selector: "node:selected", style: {
        "border-width": 4,
        "border-color": "#fff",
      }},
      // -- Trace overlay --
      // Dimmed = not on the trace path. Heavily de-emphasized so the
      // path itself is what catches the eye.
      {selector: ".dimmed", style: {
        "opacity": 0.18,
        "text-opacity": 0.4,
      }},
      // In-trace nodes get a bright halo and thicker border so they
      // pop against the dimmed background. Cytoscape's ``overlay-*``
      // properties paint a colored disc behind the node — a poor
      // man's drop shadow, but supported across all node shapes.
      {selector: "node.in-trace", style: {
        "border-width": 4,
        "border-color": "#fbbf24",
        "overlay-color": "#fbbf24",
        "overlay-opacity": 0.25,
        "overlay-padding": 6,
      }},
      // First/last trace nodes — different halo color so the "call
      // origin → call destination" reads as a flow at a glance.
      {selector: "node.trace-step-head", style: {
        "border-color": "#22c55e",
        "overlay-color": "#22c55e",
        "overlay-opacity": 0.35,
        "border-width": 5,
      }},
      {selector: "node.trace-step-tail", style: {
        "border-color": "#ef4444",
        "overlay-color": "#ef4444",
        "overlay-opacity": 0.35,
        "border-width": 5,
      }},
      // Edges between consecutive in-trace nodes — bright + thick so
      // the call's path reads as a single visual flow.
      {selector: "edge.in-trace", style: {
        "line-color": "#fbbf24",
        "target-arrow-color": "#fbbf24",
        "width": 4,
        "opacity": 1,
      }},
      // Side-panel click animation pulse — momentary highlight.
      {selector: ".trace-pulse", style: {
        "border-width": 8,
        "border-color": "#fff",
      }},
    ];
  }

  function showInfo(node) {
    const d = node.data();
    infoPane.hidden = false;
    infoLabel.textContent = d.label || "—";
    infoKind.textContent = d.kind || "";
    const extras = [];
    Object.entries(d).forEach(([k, v]) => {
      if (["id", "label", "kind", "detail_url"].includes(k)) return;
      if (v === null || v === undefined || v === "") return;
      extras.push(`<div><strong>${esc(k)}:</strong> ${esc(String(v))}</div>`);
    });
    infoExtras.innerHTML = extras.join("");
    if (d.detail_url) {
      infoLink.hidden = false;
      infoLink.href = d.detail_url;
    } else {
      infoLink.hidden = true;
    }
  }

  function pushUrlState() {
    const url = new URL(window.location.href);
    if (state.anchor) url.searchParams.set("anchor", state.anchor);
    else url.searchParams.delete("anchor");
    url.searchParams.set("direction", state.direction);
    if (state.dialed) url.searchParams.set("dialed_digits", state.dialed);
    else url.searchParams.delete("dialed_digits");
    window.history.replaceState({}, "", url);
  }

  // ---- Controls ----------------------------------------------------------

  fitBtn.addEventListener("click", () => {
    if (state.cy) state.cy.fit(undefined, 30);
  });
  relayoutBtn.addEventListener("click", () => {
    if (state.cy) state.cy.layout(dagreLayout()).run();
  });

  // ---- Initial load ------------------------------------------------------

  if (state.anchor) reloadGraph();

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({"&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"}[c]));
  }
})();
