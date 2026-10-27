/* RainReady BLR front end — vanilla JS + Leaflet */
const $ = (s) => document.querySelector(s);
const COLORS = { Critical: "#ef4444", Warning: "#f97316", Watch: "#facc15", Low: "#22c55e" };
const RES_COLORS = { desilting_crew: "#38bdf8", pump_unit: "#a78bfa", traffic_team: "#f59e0b" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- map ----------
const map = L.map("map", { zoomControl: true, attributionControl: true, preferCanvas: false }).setView([12.965, 77.62], 12);
const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18, attribution: "© OpenStreetMap contributors", className: "streets",
});
const schematic = L.layerGroup();
(function buildSchematic() {
  const B = window.BLR_BASEMAP;
  B.parks.forEach((p) => L.circle(p.c, { radius: p.r, color: "#14532d", weight: 0, fillColor: "#14532d", fillOpacity: .45, interactive: false }).addTo(schematic));
  B.lakes.forEach((l) => {
    L.circle(l.c, { radius: l.r, color: "#1d4ed8", weight: 1, fillColor: "#1e3a8a", fillOpacity: .7, interactive: false }).addTo(schematic);
    L.tooltip({ permanent: true, direction: "center", className: "basemap-label" }).setLatLng(l.c).setContent(l.name).addTo(schematic);
  });
  B.roads.forEach((r) => {
    L.polyline(r.path, { color: r.major ? "#334a75" : "#26375a", weight: r.major ? 6 : 3.5, opacity: 1, interactive: false }).addTo(schematic);
    const mid = r.path[Math.floor(r.path.length / 2)];
    L.tooltip({ permanent: true, direction: "center", className: "basemap-label" }).setLatLng(mid).setContent(r.name).addTo(schematic);
  });
})();

let basemapMode = "auto"; // auto -> streets, falls back to schematic on tile errors
let tileErrors = 0;
streets.on("tileerror", () => {
  tileErrors += 1;
  if (basemapMode === "auto" && tileErrors >= 3) useBasemap("schematic", true);
});
function useBasemap(mode, auto = false) {
  if (mode === "streets") { schematic.remove(); streets.addTo(map); }
  else { streets.remove(); schematic.addTo(map); }
  basemapMode = auto ? "schematic-auto" : mode;
  $("#basemapBtn").textContent = mode === "streets" ? "Basemap: streets" : (auto ? "Basemap: offline schematic" : "Basemap: schematic");
}
streets.addTo(map);
$("#basemapBtn").onclick = () => useBasemap(map.hasLayer(streets) ? "schematic" : "streets");

const layers = { hot: L.layerGroup().addTo(map), lines: L.layerGroup().addTo(map), depots: L.layerGroup().addTo(map), reports: L.layerGroup().addTo(map) };
let reportMode = false;
let lastRun = null;
const hotMarkers = {};

$("#reportModeBtn").onclick = () => {
  reportMode = !reportMode;
  $("#reportModeBtn").classList.toggle("on", reportMode);
  if (reportMode) switchTab("report");
};
map.on("click", (e) => {
  if (!reportMode) return;
  $("#r-lat").value = e.latlng.lat.toFixed(4);
  $("#r-lng").value = e.latlng.lng.toFixed(4);
  L.popup().setLatLng(e.latlng).setContent("Location set for report").openOn(map);
});

// ---------- tabs ----------
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tabpane").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}
document.querySelectorAll(".tab").forEach((t) => (t.onclick = () => switchTab(t.dataset.tab)));

// ---------- controls ----------
async function loadScenarios() {
  const s = await (await fetch("/api/scenarios")).json();
  $("#scenario").innerHTML = Object.entries(s).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#scenario").value = "evening_thunderstorm";
}
$("#source").onchange = () => ($("#scenarioWrap").style.opacity = $("#source").value === "live" ? .5 : 1);

// ---------- rendering ----------
function rainBars(series) {
  const max = Math.max(10, ...series);
  const w = 240, h = 60, bw = w / series.length;
  const bars = series.map((v, i) => {
    const bh = (v / max) * (h - 12);
    const c = v >= 20 ? "#ef4444" : v >= 8 ? "#f59e0b" : "#38bdf8";
    return `<rect x="${(i * bw).toFixed(1)}" y="${(h - 10 - bh).toFixed(1)}" width="${(bw - 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${c}"/>`;
  }).join("");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="48 hour rain forecast">
    ${bars}<line x1="0" y1="${h - 10}" x2="${w}" y2="${h - 10}" stroke="#22304f"/>
    <text x="0" y="${h}" fill="#8fa1c2" font-size="9">now</text><text x="${w / 2 - 8}" y="${h}" fill="#8fa1c2" font-size="9">+24h</text><text x="${w - 22}" y="${h}" fill="#8fa1c2" font-size="9">+48h</text></svg>`;
}

function popupHtml(h) {
  return `<div class="popup"><h4>${esc(h.name)} <span class="pill ${h.level}">${h.level}</span></h4>
    <div class="meta">${esc(h.zone)} zone · ${esc(h.type.replaceAll("_", " "))} · ${esc(h.catchment)}</div>
    <div class="meta">Risk ${h.risk.toFixed(2)} · ${h.max_3h_mm} mm/3h · ${h.total_24h_mm} mm/24h</div>
    <ul>${h.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    ${rainBars(lastRun.rain[h.id])}</div>`;
}

function render(data) {
  lastRun = data;
  Object.values(layers).forEach((l) => l.clearLayers());

  data.depots.forEach((d) => {
    L.marker([d.lat, d.lng], { icon: L.divIcon({ className: "", html: '<div style="width:14px;height:14px;background:#a78bfa;border:2px solid #0b1220;border-radius:3px"></div>', iconSize: [14, 14] }) })
      .bindTooltip(d.name).addTo(layers.depots);
  });

  data.plan.assigned.forEach((a) => {
    L.polyline([[a.depot_lat, a.depot_lng], [a.lat, a.lng]], {
      color: RES_COLORS[a.resource], weight: 2, opacity: .75, dashArray: "6 6",
    }).bindTooltip(`${a.resource_label} → ${a.hotspot} (ETA ${a.eta_min} min)`).addTo(layers.lines);
  });

  [...data.hotspots].reverse().forEach((h) => {
    const m = L.circleMarker([h.lat, h.lng], {
      radius: 6 + h.risk * 12, color: "#0b1220", weight: 2, fillColor: COLORS[h.level], fillOpacity: .9,
    }).bindPopup(() => popupHtml(h), { maxWidth: 280 }).addTo(layers.hot);
    hotMarkers[h.id] = m;
  });

  renderReports();

  const k = data.kpis;
  $("#k-crit").textContent = k.critical;
  $("#k-warn").textContent = k.warning;
  $("#k-units").textContent = k.units_dispatched;
  $("#k-cover").textContent = k.critical_total ? `${k.critical_covered}/${k.critical_total}` : "—";
  $("#k-lead").textContent = k.min_lead_hours != null ? `${k.min_lead_hours} h` : "—";
  $("#k-ontime").textContent = `${k.on_time_pct}%`;

  $("#brief").textContent = data.act.brief;
  $("#sourceNote").textContent = data.sense.note || `Data: ${data.sense.label}`;

  const trace = $("#trace");
  trace.innerHTML = "";
  data.trace.forEach((t, i) => {
    setTimeout(() => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="tag ${t.step}">${t.step}</span><span>${esc(t.msg)}</span>`;
      trace.appendChild(li);
    }, i * 350);
  });

  $("#hotlist").innerHTML = data.hotspots.slice(0, 8).map((h) => `
    <div class="hot" data-id="${h.id}">
      <span class="name">${esc(h.name)}</span><span class="pill ${h.level}">${h.level}</span>
      <div class="bar"><i style="width:${Math.round(h.risk * 100)}%;background:${COLORS[h.level]}"></i></div>
      <span class="meta">${esc(h.reasons[0])}</span>
    </div>`).join("");
  document.querySelectorAll(".hot").forEach((el) => (el.onclick = () => {
    const m = hotMarkers[el.dataset.id];
    map.flyTo(m.getLatLng(), 14, { duration: .6 });
    setTimeout(() => m.openPopup(), 650);
  }));

  const taskHtml = (a) => `
    <div class="task ${a.resource}">
      <div class="top"><span>${esc(a.resource_label)} → ${esc(a.hotspot)}</span><span class="pill ${a.level}">${a.level}</span></div>
      <div class="act">${esc(a.action)}</div>
      <div class="meta">${a.depot ? `From ${esc(a.depot)} · ${a.distance_km} km · ETA ${a.eta_min} min · ` : ""}peak in ${a.peak_hour_offset} h ·
        <span class="${a.status === "Before peak" ? "ok" : "late"}">${esc(a.status)}</span></div>
    </div>`;
  $("#dispatch").innerHTML = data.plan.assigned.map(taskHtml).join("") || '<p class="hint">No dispatch needed.</p>';
  $("#unassigned").innerHTML = data.plan.unassigned.map(taskHtml).join("") || '<p class="hint">None — all tasks covered.</p>';

  $("#alerts").innerHTML = data.act.alerts.map((a) => `
    <div class="alert"><div class="head"><span>${esc(a.hotspot)}</span><span class="pill ${a.level}">${a.level}</span></div>
      <div class="when">Send at ${esc(a.send_at)}</div><div>${esc(a.en)}</div><div class="kn">${esc(a.kn)}</div></div>`).join("") || '<p class="hint">No alerts needed.</p>';
  $("#advisories").innerHTML = data.act.advisories.map((a) => `<div class="alert"><span class="pill ${a.level}">${a.level}</span> ${esc(a.text)}</div>`).join("") || '<p class="hint">None.</p>';
}

async function renderReports() {
  const reps = await (await fetch("/api/reports")).json();
  layers.reports.clearLayers();
  reps.filter((r) => r.status === "open").forEach((r) => {
    L.marker([r.lat, r.lng], { icon: L.divIcon({ className: "", html: '<div style="width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:12px solid #f472b6"></div>', iconSize: [14, 12] }) })
      .bindTooltip(`${r.id} · ${r.type.replace("_", " ")} ×${r.count}<br>${esc(r.routed_to)}`).addTo(layers.reports);
  });
  $("#reports").innerHTML = reps.slice().reverse().map((r) => `
    <div class="rep"><b>${r.id}</b> · ${esc(r.type.replace("_", " "))} · ×${r.count} · <i>${esc(r.status)}</i>
      <div>${esc(r.texts[r.texts.length - 1])}</div><div class="meta">Routed to ${esc(r.routed_to)}</div></div>`).join("");
}

async function runAgent() {
  const btn = $("#runBtn");
  btn.disabled = true; btn.textContent = "Running…";
  const body = {
    source: $("#source").value, scenario: $("#scenario").value,
    desilting_crew: +$("#desilting_crew").value, pump_unit: +$("#pump_unit").value, traffic_team: +$("#traffic_team").value,
  };
  try {
    const res = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!res.ok) throw new Error(await res.text());
    render(await res.json());
    switchTab("agent");
  } catch (e) {
    $("#brief").textContent = "Run failed: " + e.message;
  } finally {
    btn.disabled = false; btn.textContent = "▶ Run agent";
  }
}
$("#runBtn").onclick = runAgent;

$("#reportForm").onsubmit = async (e) => {
  e.preventDefault();
  const body = { lat: +$("#r-lat").value, lng: +$("#r-lng").value, text: $("#r-text").value };
  const res = await fetch("/api/reports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const r = await res.json();
  $("#reportResult").innerHTML = res.ok
    ? (r.duplicate
        ? `🔁 Merged with existing report <b>${r.id}</b> (now ×${r.count}). No duplicate ticket created.`
        : `✅ Ticket <b>${r.id}</b> created · classified as <b>${esc(r.type.replace("_", " "))}</b> · routed to <b>${esc(r.routed_to)}</b>`)
      + "<br><small>Re-run the agent to see how it changes the plan.</small>"
    : "Could not submit: " + esc(JSON.stringify(r.detail || r));
  renderReports();
};

loadScenarios().then(runAgent);
