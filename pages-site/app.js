const $ = (id) => document.getElementById(id);
const numberFormat = new Intl.NumberFormat("en-US");
const compactNumber = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const dateFormat = new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });

const branchColors = {
  Legislative: "#0b6b78",
  Executive: "#a96f12",
  Judicial: "#7154a6",
};

const actionColors = {
  BUY: "#0b6b78",
  SELL: "#a13e42",
  EXCHANGE: "#7154a6",
  OTHER: "#6d7a84",
};

const eventColors = {
  direct: "#1f5d43",
  asset_specific: "#7154a6",
  jurisdictional: "#0b6b78",
  institutional: "#a96f12",
  sector_context: "#60747b",
  general_macro: "#7d8991",
  general_context: "#9aa4aa",
};

const tierLabels = {
  direct: "Direct source link",
  asset_specific: "Asset-specific context",
  jurisdictional: "Jurisdictional context",
  institutional: "Institutional context",
  sector_context: "Sector context",
  general_macro: "General macro context",
  general_context: "General context",
};

const state = {
  manifest: null,
  overview: null,
  coverage: null,
  officials: [],
  officialMap: new Map(),
  timelineIndex: null,
  eventCatalog: [],
  eventMap: new Map(),
  timelineCache: new Map(),
  marketCache: new Map(),
  selectedIds: [],
  selectedTimelines: [],
  mode: "career",
  assetFilter: "",
  eventTierFilter: "focused",
  eventWindowDays: 180,
  activeEventId: "",
  activeEventContext: null,
  selectedTradeId: "",
  zoomPercent: null,
  chartExtent: null,
  tradeChart: null,
  marketChart: null,
  zoomRenderTimer: null,
  loadToken: 0,
  marketToken: 0,
  compactLayout: window.innerWidth <= 760,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value) {
  if (!value) return "Not available";
  return dateFormat.format(new Date(`${value}T00:00:00Z`));
}

function dateMs(value) {
  if (!value) return null;
  return Date.parse(`${value}T00:00:00Z`);
}

function daysBetween(value, anchor) {
  if (!value || !anchor) return null;
  return Math.round((dateMs(value) - dateMs(anchor)) / 86400000);
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function recordState(trade) {
  if (trade.public_production_trade === true) {
    return { label: "Reviewed production", className: "production" };
  }
  if (trade.record_status === "fixture_demo") {
    return { label: "Fixture", className: "fixture" };
  }
  if (String(trade.record_status || "").includes("preview")) {
    return { label: "Official parser preview", className: "preview" };
  }
  return { label: titleCase(trade.record_status || "Source status"), className: "" };
}

function money(value) {
  if (!Number.isFinite(Number(value))) return "Not available";
  return `$${compactNumber.format(Number(value))}`;
}

function lagLabel(value) {
  return value == null || !Number.isFinite(Number(value)) ? "Review" : `${numberFormat.format(Number(value))}d`;
}

function recordPath(record) {
  return `./data/${record.path}`;
}

async function fetchJson(pathOrRecord) {
  const path = typeof pathOrRecord === "string" ? pathOrRecord : recordPath(pathOrRecord);
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Unable to load ${path} (${response.status})`);
  return response.json();
}

function setHeaderStatus(label, ready = false) {
  $("headerStatus").classList.toggle("ready", ready);
  $("headerStatus").querySelector("span:last-child").textContent = label;
}

function timelineSummary(id) {
  return (state.timelineIndex?.officials || []).find((official) => official.id === id) || null;
}

function selectedEvent() {
  if (state.activeEventContext) return state.activeEventContext;
  return state.eventMap.get(state.activeEventId) || null;
}

function parseUrlState() {
  const params = new URLSearchParams(window.location.search);
  const requestedIds = (params.get("officials") || "")
    .split(",")
    .map((value) => value.trim())
    .filter((id) => state.officialMap.has(id))
    .slice(0, 4);
  state.selectedIds = requestedIds.length
    ? requestedIds
    : [...(state.timelineIndex.default_official_ids || [])].slice(0, 4);
  const mode = params.get("mode");
  state.mode = ["career", "calendar", "event"].includes(mode) ? mode : "career";
  state.activeEventId = state.eventMap.has(params.get("event")) ? params.get("event") : "";
  if (state.mode === "event" && !state.activeEventId) state.mode = "career";
  state.assetFilter = params.get("asset") || "";
  state.eventTierFilter = ["focused", "all", "macro", "none"].includes(params.get("context"))
    ? params.get("context")
    : "focused";
  const windowDays = Number(params.get("window"));
  state.eventWindowDays = [30, 90, 180, 365].includes(windowDays) ? windowDays : 180;
}

function syncUrl() {
  const params = new URLSearchParams();
  if (state.selectedIds.length) params.set("officials", state.selectedIds.join(","));
  params.set("mode", state.mode);
  if (state.assetFilter) params.set("asset", state.assetFilter);
  if (state.activeEventId) params.set("event", state.activeEventId);
  if (state.eventTierFilter !== "focused") params.set("context", state.eventTierFilter);
  if (state.eventWindowDays !== 180) params.set("window", String(state.eventWindowDays));
  const query = params.toString();
  history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash || ""}`);
}

async function loadData() {
  try {
    setHeaderStatus("Loading dataset");
    state.manifest = await fetchJson("./data/manifest.json");
    const [overview, officials, coverage, events, timelineIndex] = await Promise.all([
      fetchJson(state.manifest.files.overview),
      fetchJson(state.manifest.files.officials_index),
      fetchJson(state.manifest.files.coverage),
      fetchJson(state.manifest.files.events),
      fetchJson(state.manifest.files.timeline_index),
    ]);
    state.overview = overview;
    state.coverage = coverage;
    state.officials = officials.officials || [];
    state.officialMap = new Map(state.officials.map((official) => [official.id, official]));
    state.eventCatalog = events.events || [];
    state.eventMap = new Map(state.eventCatalog.map((event) => [event.id, event]));
    state.timelineIndex = timelineIndex;
    parseUrlState();
    initializeControls();
    renderDatasetStatus();
    initializeCharts();
    await loadSelectedTimelines();
    setHeaderStatus(`Dataset ${state.overview.dataset_version} - ${state.overview.generated_at}`, true);
  } catch (error) {
    console.error(error);
    setHeaderStatus("Dataset unavailable");
    $("dataNotice").innerHTML = `<strong>Data unavailable</strong><span>${escapeHtml(error.message)}</span>`;
    $("tradeChart").innerHTML = '<p class="empty-state">The public dataset could not be loaded.</p>';
  }
}

function initializeControls() {
  $("eventSearch").value = selectedEvent()?.label || "";
  $("eventTierFilter").value = state.eventTierFilter;
  $("eventWindowFilter").value = String(state.eventWindowDays);
  bindControls();
  updateModeControls();
}

function initializeCharts() {
  if (!window.echarts) throw new Error("Interactive chart library did not load.");
  state.tradeChart = window.echarts.init($("tradeChart"), null, { renderer: "canvas" });
  state.tradeChart.on("click", handleChartClick);
  state.tradeChart.on("datazoom", handleDataZoom);
}

function bindControls() {
  $("officialSearch").addEventListener("input", renderOfficialResults);
  $("officialSearch").addEventListener("focus", renderOfficialResults);
  $("branchFilter").addEventListener("change", renderOfficialResults);
  $("officialResults").addEventListener("click", (event) => {
    const button = event.target.closest("[data-official-id]");
    if (!button) return;
    addOfficial(button.dataset.officialId);
  });
  $("eventSearch").addEventListener("input", renderEventResults);
  $("eventSearch").addEventListener("focus", renderEventResults);
  $("eventResults").addEventListener("click", (event) => {
    const button = event.target.closest("[data-event-id]");
    if (!button) return;
    selectEvent(button.dataset.eventId);
  });
  $("selectedOfficials").addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-official]");
    if (!button) return;
    removeOfficial(button.dataset.removeOfficial);
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".official-picker")) hideOfficialResults();
    if (!event.target.closest(".event-picker")) hideEventResults();
  });
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });
  $("presidentBaselineButton").addEventListener("click", () => {
    state.selectedIds = [...state.timelineIndex.default_official_ids].slice(0, 4);
    state.selectedTradeId = "";
    state.zoomPercent = null;
    loadSelectedTimelines();
  });
  $("assetFilter").addEventListener("change", () => {
    state.assetFilter = $("assetFilter").value;
    state.zoomPercent = null;
    renderWorkbench();
  });
  $("eventTierFilter").addEventListener("change", () => {
    state.eventTierFilter = $("eventTierFilter").value;
    renderWorkbench();
  });
  $("eventWindowFilter").addEventListener("change", () => {
    state.eventWindowDays = Number($("eventWindowFilter").value);
    state.zoomPercent = null;
    renderWorkbench();
  });
  $("resetViewButton").addEventListener("click", () => {
    state.mode = "career";
    state.assetFilter = "";
    state.eventTierFilter = "focused";
    state.eventWindowDays = 180;
    state.activeEventId = "";
    state.activeEventContext = null;
    state.selectedTradeId = "";
    state.zoomPercent = null;
    $("eventSearch").value = "";
    $("eventTierFilter").value = "focused";
    $("eventWindowFilter").value = "180";
    updateAssetOptions();
    updateModeControls();
    renderWorkbench();
  });
  $("transactionRows").addEventListener("click", (event) => {
    const row = event.target.closest("[data-trade-id]");
    if (!row) return;
    selectTrade(row.dataset.tradeId);
  });
  $("transactionRows").addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const row = event.target.closest("[data-trade-id]");
    if (!row) return;
    event.preventDefault();
    selectTrade(row.dataset.tradeId);
  });
  $("eventDetail").addEventListener("click", (event) => {
    const button = event.target.closest("[data-window-trade]");
    if (!button) return;
    selectTrade(button.dataset.windowTrade);
  });

  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      const compact = window.innerWidth <= 760;
      state.tradeChart?.resize();
      state.marketChart?.resize();
      if (compact !== state.compactLayout) {
        state.compactLayout = compact;
        renderTradeChart();
      }
    }, 120);
  });
}

function officialSearchText(official) {
  const role = official.primary_role || {};
  return [
    official.full_name,
    official.branch,
    ...official.terms,
    ...official.role_categories,
    ...official.chambers,
    ...official.congresses,
    ...official.parties,
    ...official.states,
    ...official.districts,
    role.role_title,
    role.office,
    role.agency,
    role.court,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function officialAffiliation(official) {
  const role = official.primary_role || {};
  return [
    official.branch,
    role.chamber,
    role.state,
    role.district ? `District ${role.district}` : null,
    role.office,
    role.agency,
    role.court,
  ]
    .filter(Boolean)
    .join(" / ");
}

function renderOfficialResults() {
  const query = $("officialSearch").value.trim().toLowerCase();
  const branch = $("branchFilter").value;
  if (query.length < 2 && !branch) {
    hideOfficialResults();
    return;
  }
  const matches = state.officials
    .filter((official) => (!branch || official.branch === branch) && (!query || officialSearchText(official).includes(query)))
    .slice(0, 24);
  $("officialResults").innerHTML = matches.length
    ? matches
        .map((official) => {
          const selected = state.selectedIds.includes(official.id);
          const timeline = timelineSummary(official.id);
          const stateLabel = selected ? "Selected" : timeline?.trade_count ? `${timeline.trade_count} records` : "No trade rows";
          return `
            <button class="search-result" type="button" role="option" data-official-id="${escapeHtml(official.id)}" aria-selected="${selected}">
              <span>
                <strong>${escapeHtml(official.full_name)}</strong>
                <small>${escapeHtml(officialAffiliation(official))}</small>
              </span>
              <span class="result-state">${escapeHtml(stateLabel)}</span>
            </button>`;
        })
        .join("")
    : '<p class="empty-state">No officials match these filters.</p>';
  $("officialResults").hidden = false;
  $("officialSearch").setAttribute("aria-expanded", "true");
}

function hideOfficialResults() {
  $("officialResults").hidden = true;
  $("officialSearch").setAttribute("aria-expanded", "false");
}

function eventSearchText(event) {
  return [
    event.label,
    event.description,
    event.date,
    event.event_type,
    event.source,
    ...(event.market_topic_ids || []),
    ...(event.sector_scope || []),
    ...(event.jurisdiction_scope || []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function renderEventResults() {
  const query = $("eventSearch").value.trim().toLowerCase();
  const matches = state.eventCatalog
    .filter((event) => !query || eventSearchText(event).includes(query))
    .sort((a, b) => {
      const curatedDifference = Number(b.editor_status === "curated") - Number(a.editor_status === "curated");
      return curatedDifference || b.date.localeCompare(a.date) || a.label.localeCompare(b.label);
    })
    .slice(0, 40);
  $("eventResults").innerHTML = matches.length
    ? matches
        .map(
          (event) => `
            <button class="search-result" type="button" role="option" data-event-id="${escapeHtml(event.id)}" aria-selected="${event.id === state.activeEventId}">
              <span><strong>${escapeHtml(event.label)}</strong><small>${escapeHtml(`${formatDate(event.date)} / ${titleCase(event.event_type)} / ${event.source}`)}</small></span>
              <span class="result-state">${escapeHtml(event.editor_status === "curated" ? "Curated anchor" : "Official source")}</span>
            </button>`
        )
        .join("")
    : '<p class="empty-state">No events match this search.</p>';
  $("eventResults").hidden = false;
  $("eventSearch").setAttribute("aria-expanded", "true");
}

function hideEventResults() {
  $("eventResults").hidden = true;
  $("eventSearch").setAttribute("aria-expanded", "false");
}

function selectEvent(id) {
  state.activeEventId = id;
  state.activeEventContext = null;
  state.zoomPercent = null;
  $("eventSearch").value = state.eventMap.get(id)?.label || "";
  hideEventResults();
  updateModeControls();
  renderWorkbench();
}

function addOfficial(id) {
  if (state.selectedIds.includes(id)) {
    hideOfficialResults();
    return;
  }
  if (state.selectedIds.length >= 4) {
    $("dataNotice").innerHTML = "<strong>Comparison limit</strong><span>Remove one selected official before adding another.</span>";
    return;
  }
  state.selectedIds.push(id);
  state.selectedTradeId = "";
  state.zoomPercent = null;
  $("officialSearch").value = "";
  hideOfficialResults();
  loadSelectedTimelines();
}

function removeOfficial(id) {
  state.selectedIds = state.selectedIds.filter((selectedId) => selectedId !== id);
  state.selectedTradeId = "";
  state.zoomPercent = null;
  loadSelectedTimelines();
}

function placeholderTimeline(id) {
  const official = state.officialMap.get(id);
  const periods = official?.service_periods || [];
  let disclosureStatus = "Disclosure documents have not yet been ingested for this official.";
  if (official?.branch === "Legislative") {
    disclosureStatus = (official.chambers || []).includes("Senate")
      ? "Senate disclosure documents have not yet been ingested for this official."
      : "House disclosure documents have not yet been normalized for this official.";
  } else if (official?.branch === "Judicial") {
    disclosureStatus = "Judicial financial disclosure documents have not yet been ingested for this official.";
  } else if (official?.branch === "Executive") {
    disclosureStatus = "Executive financial disclosure documents have not yet been ingested for this official.";
  }
  return {
    id,
    full_name: official?.full_name || id,
    branch: official?.branch || "Unknown",
    timeline_group: "source_backed_no_trades",
    service_periods: periods,
    active_service_days: periods.length ? periods[periods.length - 1].career_end_day + 1 : 0,
    roles: [],
    trades: [],
    events: [],
    stats: {
      trade_count: 0,
      record_status: "source_status_only",
      disclosure_status: disclosureStatus,
      confidence_label: "Source-backed official roster only",
    },
  };
}

async function loadTimeline(id) {
  if (state.timelineCache.has(id)) return state.timelineCache.get(id);
  const partition = state.manifest.partitions.timelines[id];
  if (!partition) {
    const placeholder = placeholderTimeline(id);
    state.timelineCache.set(id, placeholder);
    return placeholder;
  }
  const payload = await fetchJson(partition);
  state.timelineCache.set(id, payload.official);
  return payload.official;
}

async function loadSelectedTimelines() {
  const token = ++state.loadToken;
  renderSelectedOfficials();
  if (!state.selectedIds.length) {
    state.selectedTimelines = [];
    renderWorkbench();
    return;
  }
  $("tradeChart").setAttribute("aria-busy", "true");
  const timelines = await Promise.all(state.selectedIds.map(loadTimeline));
  if (token !== state.loadToken) return;
  state.selectedTimelines = timelines;
  $("tradeChart").setAttribute("aria-busy", "false");
  updateAssetOptions();
  renderWorkbench();
}

function renderSelectedOfficials() {
  $("selectedOfficials").innerHTML = state.selectedIds.length
    ? state.selectedIds
        .map((id) => {
          const official = state.officialMap.get(id);
          const timeline = timelineSummary(id);
          let coverage = "Disclosure documents pending";
          if (timeline?.trade_count) {
            coverage = `${numberFormat.format(timeline.trade_count)} records`;
          } else if (
            timeline?.document_count &&
            timeline.no_transaction_document_count === timeline.document_count
          ) {
            coverage = `${numberFormat.format(timeline.document_count)} reports / no reportable transactions`;
          } else if (timeline?.document_count) {
            coverage = `${numberFormat.format(timeline.document_count)} reports indexed`;
          } else if ((official?.chambers || []).includes("Senate")) {
            coverage = "Senate disclosures pending";
          }
          return `
            <div class="official-chip">
              <span><strong>${escapeHtml(official?.full_name || id)}</strong><small>${escapeHtml(`${official?.branch || "Unknown"} / ${coverage}`)}</small></span>
              <button type="button" data-remove-official="${escapeHtml(id)}" aria-label="Remove ${escapeHtml(official?.full_name || id)}">&times;</button>
            </div>`;
        })
        .join("")
    : '<span class="empty-state">Search for an official to begin a comparison.</span>';
}

function updateAssetOptions() {
  const current = state.assetFilter;
  const tickers = new Set();
  const classes = new Set();
  for (const official of state.selectedTimelines) {
    for (const trade of official.trades || []) {
      if (trade.ticker) tickers.add(trade.ticker);
      if (trade.asset_class) classes.add(trade.asset_class);
    }
  }
  $("assetFilter").innerHTML = [
    '<option value="">All disclosed assets</option>',
    classes.size
      ? `<optgroup label="Asset classes">${[...classes]
          .sort()
          .map((value) => `<option value="class:${escapeHtml(value)}">${escapeHtml(titleCase(value))}</option>`)
          .join("")}</optgroup>`
      : "",
    tickers.size
      ? `<optgroup label="Tickers and pairs">${[...tickers]
          .sort()
          .map((value) => `<option value="ticker:${escapeHtml(value)}">${escapeHtml(value)}</option>`)
          .join("")}</optgroup>`
      : "",
  ].join("");
  const valid = [...$("assetFilter").options].some((option) => option.value === current);
  state.assetFilter = valid ? current : "";
  $("assetFilter").value = state.assetFilter;
}

function setMode(mode) {
  if (mode === "event" && !selectedEvent()) return;
  state.mode = mode;
  state.zoomPercent = null;
  updateModeControls();
  renderWorkbench();
}

function updateModeControls() {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === state.mode);
  });
  $("eventModeButton").disabled = !selectedEvent();
  $("eventModeButton").title = selectedEvent() ? "Center comparison on the selected event" : "Select an event first";
}

function tradeMatchesAsset(trade) {
  if (!state.assetFilter) return true;
  const [kind, value] = state.assetFilter.split(":");
  return kind === "ticker" ? trade.ticker === value : trade.asset_class === value;
}

function tradeInModeWindow(trade) {
  if (state.mode !== "event") return true;
  const event = selectedEvent();
  if (!event) return false;
  return Math.abs(daysBetween(trade.date, event.date)) <= state.eventWindowDays;
}

function filteredTrades(official) {
  return (official.trades || []).filter((trade) => tradeMatchesAsset(trade) && tradeInModeWindow(trade));
}

function eventMatchesAsset(event) {
  if (!state.assetFilter) return true;
  const [kind, value] = state.assetFilter.split(":");
  if (kind === "ticker") return (event.ticker_scope || []).includes(value) || event.id === state.activeEventId;
  return (event.asset_scope || []).includes(value) || event.id === state.activeEventId;
}

function eventVisible(event) {
  if (event.id === state.activeEventId) return true;
  if (state.eventTierFilter === "none") return false;
  if (!eventMatchesAsset(event)) return false;
  if (state.eventTierFilter === "macro") return true;
  if (event.relationship_tier === "general_macro") return false;
  if (state.eventTierFilter === "all") return true;
  return event.display_default === true;
}

function eventInModeWindow(event) {
  if (state.mode !== "event") return true;
  const selected = selectedEvent();
  if (!selected) return false;
  return Math.abs(daysBetween(event.date, selected.date)) <= state.eventWindowDays;
}

function xValueForTrade(trade) {
  if (state.mode === "career") return trade.career_day;
  if (state.mode === "calendar") return dateMs(trade.date);
  return daysBetween(trade.date, selectedEvent()?.date);
}

function xValueForEvent(event) {
  if (state.mode === "career") return event.career_day;
  if (state.mode === "calendar") return dateMs(event.date);
  return daysBetween(event.date, selectedEvent()?.date);
}

function periodExtent(period) {
  if (state.mode === "career") return [period.career_start_day, period.career_end_day];
  if (state.mode === "calendar") return [dateMs(period.start), dateMs(period.end)];
  const event = selectedEvent();
  return [daysBetween(period.start, event?.date), daysBetween(period.end, event?.date)];
}

function calculateExtent() {
  if (state.mode === "event") {
    return { min: -state.eventWindowDays, max: state.eventWindowDays };
  }
  const values = [];
  for (const official of state.selectedTimelines) {
    for (const period of official.service_periods || []) values.push(...periodExtent(period));
    for (const trade of filteredTrades(official)) values.push(xValueForTrade(trade));
  }
  const clean = values.filter(Number.isFinite);
  if (!clean.length) return state.mode === "calendar" ? { min: dateMs("2009-01-20"), max: Date.now() } : { min: 0, max: 365 };
  return { min: Math.min(...clean), max: Math.max(...clean) };
}

function aggregateTradePoints(official, laneIndex) {
  const trades = filteredTrades(official).filter((trade) => Number.isFinite(xValueForTrade(trade)));
  const binSize = state.mode === "calendar" ? 30 * 86400000 : state.mode === "career" ? 14 : 7;
  const groups = new Map();
  for (const trade of trades) {
    const x = xValueForTrade(trade);
    const bucket = Math.floor(x / binSize);
    const key = `${bucket}:${trade.action}`;
    if (!groups.has(key)) groups.set(key, { xValues: [], trades: [], action: trade.action });
    const group = groups.get(key);
    group.xValues.push(x);
    group.trades.push(trade);
  }
  return [...groups.values()].map((group) => {
    const x = group.xValues.reduce((sum, value) => sum + value, 0) / group.xValues.length;
    const yOffset = group.action === "BUY" ? -0.09 : group.action === "SELL" ? 0.09 : 0;
    const midpoint = group.trades.reduce((sum, trade) => sum + Number(trade.value_midpoint || 0), 0);
    const minimum = group.trades.reduce((sum, trade) => sum + Number(trade.value_range_min || 0), 0);
    const maximum = group.trades.reduce((sum, trade) => sum + Number(trade.value_range_max || 0), 0);
    return {
      value: [x, laneIndex + yOffset, midpoint, group.trades.length],
      kind: "trade",
      action: group.action,
      officialId: official.id,
      officialName: official.full_name,
      trades: group.trades,
      minimum,
      maximum,
      itemStyle: { color: actionColors[group.action] || actionColors.OTHER },
    };
  });
}

function noTradeLaneLabel(official) {
  if ((official.trades || []).length) return "No matching transactions in this view";
  const stats = official.stats || {};
  if (stats.document_count && stats.no_transaction_document_count === stats.document_count) {
    return `${numberFormat.format(stats.document_count)} official reports: no reportable transactions`;
  }
  return stats.disclosure_status || "Disclosure documents not yet ingested";
}

function careerDateForDay(official, careerDay) {
  const period = (official.service_periods || []).find(
    (row) => careerDay >= row.career_start_day && careerDay <= row.career_end_day
  );
  if (!period) return null;
  return new Date(dateMs(period.start) + Math.round(careerDay - period.career_start_day) * 86400000);
}

function careerRulerLabel(careerDay, date, visibleSpan) {
  const day = Math.max(1, Math.floor(careerDay) + 1);
  const month = Math.max(1, Math.floor(careerDay / 30.4375) + 1);
  const year = Math.max(1, Math.floor(careerDay / 365.25) + 1);
  if (visibleSpan <= 62) {
    return `D${numberFormat.format(day)} · ${date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    })}`;
  }
  if (visibleSpan <= 730) {
    return `M${numberFormat.format(month)} · ${date.toLocaleDateString("en-US", {
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    })}`;
  }
  return `Y${numberFormat.format(year)} · ${date.getUTCFullYear()}`;
}

function careerRulerPoints(official, laneIndex) {
  if (state.mode !== "career" || !(official.service_periods || []).length) return [];
  const zoom = zoomedXRange() || state.chartExtent;
  const careerStart = official.service_periods[0].career_start_day;
  const careerEnd = official.service_periods[official.service_periods.length - 1].career_end_day;
  const start = Math.max(careerStart, zoom.min);
  const end = Math.min(careerEnd, zoom.max);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return [];
  const visibleSpan = Math.max(1, end - start);
  const count = state.compactLayout ? 3 : 5;
  const days = new Set();
  for (let index = 0; index < count; index += 1) {
    days.add(Math.round(start + (visibleSpan * index) / Math.max(1, count - 1)));
  }
  return [...days].flatMap((careerDay) => {
    const date = careerDateForDay(official, careerDay);
    if (!date) return [];
    return [
      {
        value: [careerDay, laneIndex + 0.29],
        label: { formatter: careerRulerLabel(careerDay, date, visibleSpan) },
      },
    ];
  });
}

function buildChartSeries() {
  const serviceSeries = [];
  const tradePoints = [];
  const eventPoints = [];
  const breakPoints = [];
  const emptyPoints = [];
  const dateRulerPoints = [];
  const extent = state.chartExtent;

  state.selectedTimelines.forEach((official, laneIndex) => {
    (official.service_periods || []).forEach((period, periodIndex) => {
      let [start, end] = periodExtent(period);
      if (!Number.isFinite(start) || !Number.isFinite(end)) return;
      if (state.mode === "event") {
        if (end < extent.min || start > extent.max) return;
        start = clamp(start, extent.min, extent.max);
        end = clamp(end, extent.min, extent.max);
      }
      serviceSeries.push({
        name: `${official.full_name} service`,
        type: "line",
        silent: true,
        symbol: "none",
        data: [[start, laneIndex], [end, laneIndex]],
        lineStyle: { width: 7, color: branchColors[official.branch] || "#0b6b78", opacity: 0.66 },
        emphasis: { disabled: true },
        animation: false,
        z: 1,
      });
      if (periodIndex > 0 && state.mode === "career") {
        breakPoints.push({
          value: [period.career_start_day, laneIndex],
          officialName: official.full_name,
          period,
        });
      }
    });

    const points = aggregateTradePoints(official, laneIndex);
    tradePoints.push(...points);
    dateRulerPoints.push(...careerRulerPoints(official, laneIndex));
    if (!points.length) {
      emptyPoints.push({
        value: [extent.min + (extent.max - extent.min) * 0.08, laneIndex],
        label: { formatter: noTradeLaneLabel(official) },
      });
    }

    for (const relationship of official.events || []) {
      const event = { ...(state.eventMap.get(relationship.id) || {}), ...relationship };
      if (!eventVisible(event) || !eventInModeWindow(event)) continue;
      const x = xValueForEvent(event);
      if (!Number.isFinite(x)) continue;
      eventPoints.push({
        value: [x, laneIndex - 0.24, event.relationship_tier_rank || 0],
        kind: "event",
        officialId: official.id,
        officialName: official.full_name,
        event,
        itemStyle: { color: eventColors[event.relationship_tier] || eventColors.general_context },
      });
    }
  });

  return [
    ...serviceSeries,
    {
      name: "Local career dates",
      type: "scatter",
      silent: true,
      data: dateRulerPoints,
      symbol: "rect",
      symbolSize: [1, 5],
      itemStyle: { color: "#aebdb6" },
      label: {
        show: true,
        position: "bottom",
        distance: 3,
        color: "#53616a",
        fontSize: 9,
      },
      labelLayout: { hideOverlap: true },
      z: 3,
    },
    {
      name: "Term break",
      type: "scatter",
      silent: true,
      data: breakPoints,
      symbol: "rect",
      symbolSize: [4, 22],
      itemStyle: { color: "#ffffff", borderColor: "#17212b", borderWidth: 1 },
      z: 3,
    },
    {
      name: "Transactions",
      type: "scatter",
      data: tradePoints,
      symbol: "circle",
      symbolSize: (value) => clamp(8 + Math.log2(Math.max(1, value[3])) * 4 + Math.log10(Math.max(10, value[2])) * 0.7, 9, 25),
      itemStyle: { borderColor: "#ffffff", borderWidth: 1.5, opacity: 0.88 },
      emphasis: { scale: 1.35 },
      z: 5,
    },
    {
      name: "Events",
      type: "scatter",
      data: eventPoints,
      symbol: "diamond",
      symbolSize: (value) => clamp(10 + Number(value[2] || 0), 10, 17),
      itemStyle: { borderColor: "#ffffff", borderWidth: 1 },
      emphasis: { scale: 1.4 },
      z: 4,
    },
    {
      name: "Empty lanes",
      type: "scatter",
      silent: true,
      data: emptyPoints,
      symbolSize: 1,
      itemStyle: { opacity: 0 },
      label: {
        show: true,
        position: "right",
        color: "#6d7a84",
        fontSize: 11,
        width: state.compactLayout ? 210 : 360,
        overflow: "break",
        lineHeight: 15,
      },
      z: 2,
    },
  ];
}

function axisLabel(value) {
  if (state.mode === "career") {
    if (value <= 0) return "Start";
    const years = value / 365.25;
    return years < 1 ? `${Math.round(value)}d` : `Y${years.toFixed(years >= 5 ? 0 : 1)}`;
  }
  if (state.mode === "event") return value === 0 ? "Event" : `${value > 0 ? "+" : ""}${Math.round(value)}d`;
  const date = new Date(value);
  return state.chartExtent.max - state.chartExtent.min > 3 * 365 * 86400000
    ? String(date.getUTCFullYear())
    : date.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}

function tooltipFormatter(params) {
  const data = params.data || {};
  if (data.kind === "trade") {
    const first = data.trades[0];
    const dates = data.trades.map((trade) => trade.date).sort();
    const stateInfo = recordState(first);
    return `
      <strong>${escapeHtml(data.officialName)}</strong><br>
      ${escapeHtml(data.action)} / ${numberFormat.format(data.trades.length)} transaction${data.trades.length === 1 ? "" : "s"}<br>
      ${escapeHtml(formatDate(dates[0]))}${dates.length > 1 ? ` to ${escapeHtml(formatDate(dates[dates.length - 1]))}` : ""}<br>
      Disclosed aggregate range: ${escapeHtml(money(data.minimum))} to ${escapeHtml(money(data.maximum))}<br>
      <span>${escapeHtml(stateInfo.label)}</span>`;
  }
  if (data.kind === "event") {
    const event = data.event;
    const candidate = event.trade_context_candidate
      ? `<br><strong>Context candidate</strong> / ${escapeHtml(
          event.nearest_trade_days === 0
            ? "same day as nearest transaction"
            : `${Math.abs(event.nearest_trade_days)}d ${event.nearest_trade_days > 0 ? "after" : "before"} nearest transaction`
        )}`
      : "";
    return `
      <strong>${escapeHtml(event.label)}</strong><br>
      ${escapeHtml(formatDate(event.date))} / ${escapeHtml(titleCase(event.event_type))}<br>
      ${escapeHtml(tierLabels[event.relationship_tier] || "Context")}<br>
      <span>${escapeHtml((event.relationship_reasons || []).join("; "))}</span>${candidate}`;
  }
  return "";
}

function renderTradeChart() {
  if (!state.tradeChart) return;
  if (!state.selectedTimelines.length) {
    state.tradeChart.clear();
    state.tradeChart.setOption({
      graphic: {
        type: "text",
        left: "center",
        top: "middle",
        style: {
          text: "Select at least one official to build a comparison.",
          fill: "#6d7a84",
          font: "600 13px system-ui, sans-serif",
          textAlign: "center",
        },
      },
    });
    return;
  }
  state.chartExtent = calculateExtent();
  const names = state.selectedTimelines.map((official) => official.full_name);
  const chartHeight = Math.max(state.compactLayout ? 430 : 440, 210 + names.length * (state.compactLayout ? 78 : 86));
  $("tradeChart").style.height = `${chartHeight}px`;
  state.tradeChart.resize();
  const xAxis = {
    type: state.mode === "calendar" ? "time" : "value",
    min: state.chartExtent.min,
    max: state.chartExtent.max,
    axisLabel: { color: "#6d7a84", fontSize: 11, formatter: axisLabel, hideOverlap: true },
    axisLine: { lineStyle: { color: "#aebdb6" } },
    splitLine: { show: true, lineStyle: { color: "#e3e9e6" } },
  };
  const zoom = state.zoomPercent || { start: 0, end: 100 };
  state.tradeChart.setOption(
    {
      animationDuration: 250,
      grid: {
        left: state.compactLayout ? 108 : 178,
        right: state.compactLayout ? 18 : 32,
        top: 34,
        bottom: 88,
        containLabel: false,
      },
      tooltip: {
        trigger: "item",
        confine: true,
        backgroundColor: "#17212b",
        borderWidth: 0,
        textStyle: { color: "#ffffff", fontSize: 12 },
        formatter: tooltipFormatter,
      },
      xAxis,
      yAxis: {
        type: "value",
        inverse: true,
        min: -0.55,
        max: Math.max(0.55, names.length - 0.45),
        interval: 1,
        axisLabel: {
          color: "#17212b",
          fontSize: state.compactLayout ? 10 : 12,
          fontWeight: 700,
          width: state.compactLayout ? 92 : 155,
          overflow: "truncate",
          formatter: (value) => names[Math.round(value)] || "",
        },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { show: true, lineStyle: { color: "#eef2f0" } },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, filterMode: "none", start: zoom.start, end: zoom.end },
        {
          type: "slider",
          xAxisIndex: 0,
          filterMode: "none",
          start: zoom.start,
          end: zoom.end,
          bottom: 24,
          height: 24,
          borderColor: "#c5d1cc",
          fillerColor: "rgba(11,107,120,0.16)",
          handleStyle: { color: "#0b6b78" },
          textStyle: { color: "#6d7a84", fontSize: 10 },
        },
      ],
      series: buildChartSeries(),
    },
    true
  );
}

function handleChartClick(params) {
  const data = params.data || {};
  if (data.kind === "event") {
    state.activeEventId = data.event.id;
    state.activeEventContext = data.event;
    $("eventSearch").value = data.event.label || state.eventMap.get(data.event.id)?.label || "";
    updateModeControls();
    renderWorkbench();
    return;
  }
  if (data.kind === "trade" && data.trades?.length) {
    selectTrade(data.trades[0].id);
  }
}

function handleDataZoom(event) {
  const zoom = event.batch?.[0] || event;
  if (!Number.isFinite(zoom.start) || !Number.isFinite(zoom.end)) return;
  state.zoomPercent = { start: zoom.start, end: zoom.end };
  renderTransactions();
  window.clearTimeout(state.zoomRenderTimer);
  state.zoomRenderTimer = window.setTimeout(() => renderTradeChart(), 120);
}

function zoomedXRange() {
  if (!state.chartExtent || !state.zoomPercent) return state.chartExtent;
  const span = state.chartExtent.max - state.chartExtent.min;
  return {
    min: state.chartExtent.min + (span * state.zoomPercent.start) / 100,
    max: state.chartExtent.min + (span * state.zoomPercent.end) / 100,
  };
}

function visibleTransactionRows() {
  const zoom = zoomedXRange();
  return state.selectedTimelines
    .flatMap((official) =>
      filteredTrades(official).map((trade) => ({ ...trade, officialId: official.id, officialName: official.full_name }))
    )
    .filter((trade) => {
      const x = xValueForTrade(trade);
      return !zoom || !Number.isFinite(x) || (x >= zoom.min && x <= zoom.max);
    })
    .sort((a, b) => b.date.localeCompare(a.date) || a.officialName.localeCompare(b.officialName));
}

function renderTransactions() {
  const rows = visibleTransactionRows();
  $("transactionCount").textContent = `${numberFormat.format(rows.length)} record${rows.length === 1 ? "" : "s"}`;
  $("transactionRows").innerHTML = rows.length
    ? rows
        .slice(0, 500)
        .map((trade) => {
          const stateInfo = recordState(trade);
          return `
            <tr data-trade-id="${escapeHtml(trade.id)}" class="${trade.id === state.selectedTradeId ? "selected" : ""}" tabindex="0" aria-selected="${trade.id === state.selectedTradeId}">
              <td><strong>${escapeHtml(trade.officialName)}</strong><small>${escapeHtml(state.officialMap.get(trade.officialId)?.branch || "")}</small></td>
              <td>${escapeHtml(formatDate(trade.date))}</td>
              <td>${escapeHtml(formatDate(trade.reported_date))}</td>
              <td><strong>${escapeHtml(trade.action)}</strong></td>
              <td><strong>${escapeHtml(trade.ticker || trade.asset_display_name)}</strong><small>${escapeHtml(trade.asset_display_name)}</small></td>
              <td>${escapeHtml(trade.value_range_label)}</td>
              <td>${escapeHtml(lagLabel(trade.disclosure_lag_days))}</td>
              <td><span class="state-label ${stateInfo.className}">${escapeHtml(stateInfo.label)}</span></td>
            </tr>`;
        })
        .join("")
    : '<tr><td colspan="8" class="empty-state">No transaction records match this view.</td></tr>';
}

function findTrade(id) {
  for (const official of state.selectedTimelines) {
    const trade = (official.trades || []).find((row) => row.id === id);
    if (trade) return { trade, official };
  }
  return null;
}

function selectTrade(id) {
  state.selectedTradeId = id;
  renderRecordDetail();
  renderTransactions();
}

function renderRecordDetail() {
  const found = findTrade(state.selectedTradeId);
  if (!found) {
    $("recordDetail").innerHTML = `
      <p class="eyebrow">Transaction evidence</p>
      <h2>Select a transaction marker or row</h2>
      <p>Source document, filing lag, record state, and parser evidence will appear here.</p>`;
    return;
  }
  const { trade, official } = found;
  const stateInfo = recordState(trade);
  const sourceLink = trade.source_url
    ? `<a href="${escapeHtml(trade.source_url)}" target="_blank" rel="noopener noreferrer">Official source document</a>`
    : "";
  const price = trade.price_window?.closest_close;
  const benchmark = trade.benchmark_price_window?.closest_close;
  $("recordDetail").innerHTML = `
    <p class="eyebrow">Transaction evidence</p>
    <h2>${escapeHtml(`${official.full_name}: ${trade.action} ${trade.ticker || trade.asset_display_name}`)}</h2>
    <p>${escapeHtml(trade.asset_display_name)} / ${escapeHtml(trade.value_range_label)}</p>
    <div class="detail-meta">
      <span>Trade ${escapeHtml(formatDate(trade.date))}</span>
      <span>Reported ${escapeHtml(formatDate(trade.reported_date))}</span>
      <span>${escapeHtml(lagLabel(trade.disclosure_lag_days))} filing lag</span>
      <span>${escapeHtml(titleCase(trade.asset_class))}</span>
      <span class="state-label ${stateInfo.className}">${escapeHtml(stateInfo.label)}</span>
    </div>
    <div class="detail-meta">
      ${price ? `<span>${escapeHtml(trade.ticker)} close ${escapeHtml(price)}</span>` : ""}
      ${benchmark ? `<span>${escapeHtml(trade.benchmark_symbol)} close ${escapeHtml(benchmark)}</span>` : ""}
      ${trade.parsing_confidence != null ? `<span>Parser confidence ${Math.round(Number(trade.parsing_confidence) * 100)}%</span>` : ""}
      ${trade.source_page ? `<span>Source page ${numberFormat.format(trade.source_page)}</span>` : ""}
      ${trade.filing_label ? `<span>${escapeHtml(trade.filing_label)}</span>` : ""}
    </div>
    <div class="evidence-links">${sourceLink || '<span class="state-label">Source link unavailable in this snapshot</span>'}</div>
    ${
      trade.decision_authority_note
        ? `<p class="evidence-note"><strong>Decision authority recorded in filing:</strong> ${escapeHtml(trade.decision_authority_note)}</p>`
        : `<p class="evidence-note">${escapeHtml(
            trade.disclosure_attribution_note ||
              "This transaction appears on the official's disclosure; the source filing controls ownership and decision-authority attribution."
          )}</p>`
    }
    <p>No causation, intent, ethics, legality, or investment conclusion is implied.</p>`;
}

function transactionsInsideEventWindow(event) {
  if (!event) return [];
  return state.selectedTimelines
    .flatMap((official) =>
      (official.trades || [])
        .filter(tradeMatchesAsset)
        .map((trade) => ({ ...trade, officialName: official.full_name, daysFromEvent: daysBetween(trade.date, event.date) }))
    )
    .filter((trade) => Math.abs(trade.daysFromEvent) <= state.eventWindowDays)
    .sort((a, b) => Math.abs(a.daysFromEvent) - Math.abs(b.daysFromEvent))
    .slice(0, 16);
}

function renderEventDetail() {
  const event = selectedEvent();
  if (!event) {
    $("eventDetail").innerHTML = `
      <p class="eyebrow">Event evidence</p>
      <h2>Select an event marker</h2>
      <p>Event evidence and transactions inside the chosen time window will appear here.</p>`;
    return;
  }
  const transactions = transactionsInsideEventWindow(event);
  const sources = (event.source_urls || [])
    .map((url, index) => `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1}</a>`)
    .join("");
  const reasons = event.relationship_reasons || [];
  const candidateTiming = event.trade_context_candidate
    ? event.nearest_trade_days === 0
      ? "Same day as the nearest disclosed transaction"
      : `${Math.abs(event.nearest_trade_days)} days ${event.nearest_trade_days > 0 ? "after" : "before"} the nearest disclosed transaction`
    : "";
  const sourceReference = event.docket_number
    ? `Docket ${event.docket_number}${event.citation ? ` / ${event.citation}` : ""}`
    : event.law_number
      ? `Public Law ${event.law_number}`
      : event.executive_order_number
        ? `Executive Order ${event.executive_order_number}`
        : "";
  $("eventDetail").innerHTML = `
    <p class="eyebrow">${escapeHtml(titleCase(event.event_type))} / ${escapeHtml(formatDate(event.date))}</p>
    <h2>${escapeHtml(event.label)}</h2>
    <p>${escapeHtml(event.description || "No event summary is available.")}</p>
    <div class="detail-meta">
      <span>${escapeHtml(tierLabels[event.relationship_tier] || "Global context")}</span>
      <span>${escapeHtml(event.editor_status || "source status")}</span>
      <span>${escapeHtml(event.source || "CivicLedger event source")}</span>
      ${sourceReference ? `<span>${escapeHtml(sourceReference)}</span>` : ""}
      ${event.trade_context_candidate ? '<span class="state-label preview">Automated context candidate</span>' : ""}
    </div>
    ${reasons.length ? `<p>${escapeHtml(reasons.join("; "))}</p>` : ""}
    ${
      candidateTiming
        ? `<p class="evidence-note"><strong>${escapeHtml(candidateTiming)}.</strong> This marker is selected from source-backed public events by timing and entity or institutional relevance. It does not establish knowledge, intent, causation, or market impact.</p>`
        : ""
    }
    <div class="evidence-links">${sources || '<span class="state-label">No source link recorded</span>'}</div>
    <div class="window-transactions">
      <strong>Transactions within ${numberFormat.format(state.eventWindowDays)} days:</strong>
      ${
        transactions.length
          ? transactions
              .map(
                (trade) =>
                  `<button type="button" data-window-trade="${escapeHtml(trade.id)}">${escapeHtml(trade.officialName)} / ${escapeHtml(trade.action)} ${escapeHtml(trade.ticker || trade.asset_display_name)} / ${trade.daysFromEvent > 0 ? "+" : ""}${numberFormat.format(trade.daysFromEvent)}d</button>`
              )
              .join("")
          : '<span class="state-label">None in selected lanes</span>'
      }
    </div>`;
}

function renderSummary() {
  const trades = state.selectedTimelines.flatMap(filteredTrades);
  const production = trades.filter((trade) => trade.public_production_trade === true).length;
  const preview = trades.filter((trade) => String(trade.record_status || "").includes("preview")).length;
  const tickerMapped = trades.filter((trade) => trade.ticker).length;
  const events = state.selectedTimelines.reduce(
    (total, official) => total + (official.events || []).filter(eventVisible).filter(eventInModeWindow).length,
    0
  );
  const metrics = [
    [state.selectedTimelines.length, "Officials"],
    [trades.length, "Transactions"],
    [production, "Reviewed production"],
    [preview, "Official preview"],
    [tickerMapped, "Ticker-mapped"],
    [events, "Visible context markers"],
  ];
  $("workbenchSummary").innerHTML = metrics
    .map(([value, label]) => `<div class="summary-item"><strong>${numberFormat.format(value)}</strong><span>${escapeHtml(label)}</span></div>`)
    .join("");
}

function renderChartHeader() {
  const modeCopy = {
    career: [
      "Career trade activity",
      "Active service time is cumulative; each lane's local date ruler changes from years to months to days as you zoom.",
    ],
    calendar: ["Calendar trade activity", "Officials, transactions, and events share actual dates; inactive service gaps remain visible."],
    event: [
      selectedEvent() ? `${selectedEvent().label} event window` : "Event window",
      `The selected event is day 0; transactions are shown within ${numberFormat.format(state.eventWindowDays)} days before and after.`,
    ],
  };
  $("chartTitle").textContent = modeCopy[state.mode][0];
  $("chartDescription").textContent = modeCopy[state.mode][1];
}

function renderChartAlternative() {
  const descriptions = state.selectedTimelines.map((official) => {
    const trades = filteredTrades(official);
    const buys = trades.filter((trade) => trade.action === "BUY").length;
    const sells = trades.filter((trade) => trade.action === "SELL").length;
    return `${official.full_name}, ${official.branch}: ${trades.length} displayed transactions, ${buys} buys, ${sells} sells, ${(official.service_periods || []).length} service periods.`;
  });
  $("chartAlternative").textContent = descriptions.join(" ");
}

async function loadMarket(symbol) {
  if (!symbol) return null;
  if (state.marketCache.has(symbol)) return state.marketCache.get(symbol);
  const partition = state.manifest.partitions.market[symbol];
  if (!partition) return null;
  const payload = await fetchJson(partition);
  state.marketCache.set(symbol, payload);
  return payload;
}

function marketPointValue(point) {
  return point.adj_close ?? point.close ?? point.value ?? null;
}

async function renderMarketChart() {
  const token = ++state.marketToken;
  const [kind, symbol] = state.assetFilter.split(":");
  if (kind !== "ticker" || !symbol || state.mode === "career") {
    $("marketShell").hidden = true;
    return;
  }
  const matchingTrade = state.selectedTimelines
    .flatMap((official) => official.trades || [])
    .find((trade) => trade.ticker === symbol);
  const benchmark = matchingTrade?.benchmark_symbol || "SPY";
  const [assetData, benchmarkData] = await Promise.all([loadMarket(symbol), loadMarket(benchmark)]);
  if (token !== state.marketToken) return;
  $("marketShell").hidden = false;
  if (!state.marketChart) state.marketChart = window.echarts.init($("marketChart"), null, { renderer: "canvas" });
  state.marketChart.resize();
  const event = selectedEvent();
  const extent = state.mode === "event"
    ? { min: dateMs(event.date) - state.eventWindowDays * 86400000, max: dateMs(event.date) + state.eventWindowDays * 86400000 }
    : state.chartExtent;

  function normalizedSeries(payload, name) {
    const points = (payload?.points || [])
      .map((point) => [dateMs(point.date), Number(marketPointValue(point))])
      .filter(([dateValue, value]) => Number.isFinite(dateValue) && Number.isFinite(value) && dateValue >= extent.min && dateValue <= extent.max);
    if (!points.length) return { name, data: [] };
    const baseline = points[0][1];
    return { name, data: points.map(([dateValue, value]) => [dateValue, Number(((value / baseline) * 100).toFixed(3))]) };
  }

  const assetSeries = normalizedSeries(assetData, symbol);
  const benchmarkSeries = normalizedSeries(benchmarkData, benchmark);
  $("marketTitle").textContent = `${symbol} and ${benchmark} normalized price context`;
  state.marketChart.setOption(
    {
      animationDuration: 200,
      grid: { left: state.compactLayout ? 48 : 64, right: 24, top: 28, bottom: 54 },
      tooltip: { trigger: "axis", valueFormatter: (value) => Number(value).toFixed(2) },
      legend: { top: 0, textStyle: { color: "#4f5d68" } },
      xAxis: { type: "time", min: extent.min, max: extent.max, axisLabel: { color: "#6d7a84", hideOverlap: true } },
      yAxis: { type: "value", name: "Indexed", axisLabel: { color: "#6d7a84" }, splitLine: { lineStyle: { color: "#e3e9e6" } } },
      series: [
        { type: "line", name: assetSeries.name, data: assetSeries.data, showSymbol: false, lineStyle: { width: 2.5, color: "#0b6b78" }, itemStyle: { color: "#0b6b78" } },
        { type: "line", name: benchmarkSeries.name, data: benchmarkSeries.data, showSymbol: false, lineStyle: { width: 2, color: "#a96f12" }, itemStyle: { color: "#a96f12" } },
      ],
      graphic:
        assetSeries.data.length || benchmarkSeries.data.length
          ? []
          : [{ type: "text", left: "center", top: "middle", style: { text: "No market data is available for this date range.", fill: "#6d7a84" } }],
    },
    true
  );
}

function renderDatasetStatus() {
  const summary = state.overview.summary;
  $("dataNotice").innerHTML = `
    <strong>Current record boundary</strong>
    <span>${escapeHtml(state.overview.disclaimer)} Reviewed public production trades: ${numberFormat.format(summary.reviewed_public_trade_count || 0)}.</span>`;
  $("footerDataset").textContent = `Dataset ${state.overview.dataset_version} / generated ${state.overview.generated_at}`;

  const metrics = [
    [summary.tracked_public_official_count, "Tracked officials"],
    [summary.house_ptr_processed_document_count, "House PTR documents"],
    [summary.house_ptr_machine_readable_document_count, "Machine-readable PTRs"],
    [summary.house_ptr_parser_preview_transaction_count, "House preview rows"],
    [summary.house_ptr_ocr_required_document_count, "OCR backlog"],
    [summary.market_price_point_count + summary.crypto_price_point_count, "Market price points"],
  ];
  $("coverageMetrics").innerHTML = metrics
    .map(([value, label]) => `<div class="coverage-card"><strong>${numberFormat.format(value || 0)}</strong><span>${escapeHtml(label)}</span></div>`)
    .join("");

  const peopleByBranch = state.officials.reduce((counts, official) => {
    counts[official.branch] = (counts[official.branch] || 0) + 1;
    return counts;
  }, {});
  $("branchStatus").innerHTML = ["Legislative", "Executive", "Judicial"]
    .map((branch) => {
      const timeline = state.coverage.timeline_by_branch[branch] || {};
      const roles = summary.public_official_role_counts_by_branch[branch] || 0;
      return `
        <article class="branch-card ${escapeHtml(branch)}">
          <h3>${escapeHtml(branch)}</h3>
          <dl>
            <dt>Tracked officials</dt><dd>${numberFormat.format(peopleByBranch[branch] || 0)}</dd>
            <dt>Role records</dt><dd>${numberFormat.format(roles)}</dd>
            <dt>Timeline trade rows</dt><dd>${numberFormat.format(timeline.trades || 0)}</dd>
            <dt>Reviewed production</dt><dd>${numberFormat.format(timeline.production_trades || 0)}</dd>
          </dl>
        </article>`;
    })
    .join("");

  $("sourceStatus").innerHTML = state.overview.sources
    .map(
      (source) => `
        <article class="source-row">
          <div><h3>${escapeHtml(source.name)}</h3><small>${escapeHtml(source.branch)}</small></div>
          <span class="state-label">${escapeHtml(titleCase(source.ingestion_status))}</span>
          <p>${escapeHtml((source.readiness?.missing_capabilities || []).join(" / ") || "No missing capability recorded")}</p>
          <a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">Official source</a>
        </article>`
    )
    .join("");
  $("releaseBlockers").innerHTML = `
    <strong>Release blockers</strong>
    <ul>${state.coverage.release_blockers.map((blocker) => `<li>${escapeHtml(blocker)}</li>`).join("")}</ul>`;
}

function renderWorkbench() {
  updateModeControls();
  renderSelectedOfficials();
  renderChartHeader();
  renderSummary();
  renderTradeChart();
  renderChartAlternative();
  renderEventDetail();
  renderRecordDetail();
  renderTransactions();
  renderMarketChart();
  syncUrl();
}

loadData();
