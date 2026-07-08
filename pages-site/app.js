const state = {
  data: null,
  explorerPeople: [],
  selectedId: null,
  comparisonIds: [],
  query: "",
  branch: "",
  roleCategory: "",
  term: "",
  chamber: "",
  congressNumber: "",
  party: "",
  officialState: "",
  district: "",
  timelineAxis: "career",
  timelineZoom: "full",
  timelineOfficialQuery: "",
  timelineAssetClass: "",
  timelineOverlay: "all",
  timelineEventType: "",
  activeTimelineEventId: null,
};

const fmt = new Intl.NumberFormat("en-US");

const branchColors = {
  Legislative: "#0b6b8f",
  Executive: "#b66a1d",
  Judicial: "#7154a6",
};

const branchOrder = ["Legislative", "Executive", "Judicial"];

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function compact(parts) {
  return parts.filter(Boolean).join(" / ");
}

function shortDate(value) {
  if (!value) return "Unknown";
  return new Date(`${value}T00:00:00`).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function termLabel(termId) {
  return state.data.public_officials?.scope?.presidential_terms?.[termId]?.label || termId;
}

function roleSortValue(role) {
  return role.service_start || "0000-00-00";
}

function roleCategoryLabel(value) {
  return String(value || "").replaceAll("_", " ");
}

function signedPct(value) {
  if (value === null || value === undefined) return "n/a";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${Number(value).toFixed(2)}%`;
}

function latestObservation(series) {
  if (!series?.observations?.length) return null;
  return [...series.observations].reverse().find((row) => row.value !== null && row.value !== undefined) || null;
}

function formatMacroValue(value, units) {
  if (value === null || value === undefined) return "n/a";
  if (units === "0 or 1") return Number(value) === 1 ? "Recession" : "Expansion";
  return `${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })}${units === "Percent" ? "%" : ""}`;
}

function moveList(moves) {
  return (moves || [])
    .map((move) => `${move.horizon_days || move.label}: ${signedPct(move.pct_change)}`)
    .join(" / ");
}

function sparkline(points, label) {
  if (!points?.length) return '<span class="muted">No price path</span>';
  const width = 190;
  const height = 54;
  const values = points.map((point) => Number(point.value)).filter(Number.isFinite);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(0.0001, max - min);
  const step = points.length > 1 ? width / (points.length - 1) : width;
  const path = points
    .map((point, index) => {
      const x = index * step;
      const y = height - 8 - ((Number(point.value) - min) / span) * (height - 16);
      return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return `
    <svg class="sparkline" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(label)}">
      <path d="${path}" fill="none" stroke="#0b6b8f" stroke-width="2"></path>
    </svg>
  `;
}

function affiliation(person) {
  if (!person.primary_role) return person.branch;
  const metadata = person.primary_role.source_metadata || {};
  return compact([
    person.branch,
    metadata.chamber,
    metadata.congress_number ? `${metadata.congress_number}th Congress` : null,
    metadata.state,
    metadata.district ? `District ${metadata.district}` : null,
    termLabel(person.primary_role.presidential_term),
    person.primary_role.office,
    person.primary_role.agency,
    person.primary_role.court,
  ]);
}

function buildExplorerPeople() {
  const rolesByPerson = new Map();
  for (const role of state.data.public_officials.roles) {
    if (!rolesByPerson.has(role.external_person_id)) {
      rolesByPerson.set(role.external_person_id, []);
    }
    rolesByPerson.get(role.external_person_id).push(role);
  }

  state.explorerPeople = state.data.public_officials.people
    .map((person) => {
      const roles = [...(rolesByPerson.get(person.external_person_id) || [])].sort((a, b) =>
        roleSortValue(b).localeCompare(roleSortValue(a))
      );
      const primaryRole = roles.find((role) => !role.service_end) || roles[0] || null;
      return {
        id: person.external_person_id,
        full_name: person.full_name,
        branch: person.branch,
        roles,
        primary_role: primaryRole,
        role_terms: [...new Set(roles.map((role) => role.presidential_term))],
        role_categories: [...new Set(roles.map((role) => role.role_category))],
        chambers: [...new Set(roles.map((role) => role.source_metadata?.chamber).filter(Boolean))],
        congress_numbers: [...new Set(roles.map((role) => role.source_metadata?.congress_number).filter(Boolean))],
        parties: [...new Set(roles.map((role) => role.source_metadata?.party).filter(Boolean))],
        states: [...new Set(roles.map((role) => role.source_metadata?.state).filter(Boolean))],
        districts: [...new Set(roles.map((role) => role.source_metadata?.district).filter(Boolean))],
      };
    })
    .sort((a, b) => {
      const branchCompare = a.branch.localeCompare(b.branch);
      return branchCompare || a.full_name.localeCompare(b.full_name);
    });
}

function branchPeopleCounts() {
  const counts = Object.fromEntries(branchOrder.map((branch) => [branch, 0]));
  for (const person of state.explorerPeople) {
    counts[person.branch] = (counts[person.branch] || 0) + 1;
  }
  return counts;
}

function roleCategoryCounts() {
  return state.data.public_officials.roles.reduce((counts, role) => {
    counts[role.role_category] = (counts[role.role_category] || 0) + 1;
    return counts;
  }, {});
}

function personMatchesQuery(person, query) {
  if (!query) return true;
  const haystack = [
    person.full_name,
    person.branch,
    ...person.roles.flatMap((role) => [
      role.presidential_term,
      termLabel(role.presidential_term),
      role.administration,
      role.role_category,
      role.role_title,
      role.office,
      role.agency,
      role.court,
      role.appointing_president,
      role.source_name,
      role.source_metadata?.bioguide_id,
      role.source_metadata?.congress_number,
      role.source_metadata?.chamber,
      role.source_metadata?.party,
      role.source_metadata?.state,
      role.source_metadata?.district,
    ]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function roleMatchesFilters(role) {
  const metadata = role.source_metadata || {};
  return (
    (!state.roleCategory || role.role_category === state.roleCategory) &&
    (!state.term || role.presidential_term === state.term) &&
    (!state.chamber || metadata.chamber === state.chamber) &&
    (!state.congressNumber || String(metadata.congress_number) === state.congressNumber) &&
    (!state.party || metadata.party === state.party) &&
    (!state.officialState || metadata.state === state.officialState) &&
    (!state.district || String(metadata.district || "") === state.district)
  );
}

function filteredPeople() {
  const query = state.query.trim().toLowerCase();
  return state.explorerPeople.filter((person) => {
    const branchOk = !state.branch || person.branch === state.branch;
    const roleOk = person.roles.some((role) => roleMatchesFilters(role));
    return branchOk && roleOk && personMatchesQuery(person, query);
  });
}

function peopleByIds(ids) {
  const byId = new Map(state.explorerPeople.map((person) => [person.id, person]));
  return ids.map((id) => byId.get(id)).filter(Boolean);
}

function ensureComparisonHas(personId) {
  if (!personId) return;
  if (!state.comparisonIds.includes(personId)) {
    state.comparisonIds = [personId, ...state.comparisonIds].slice(0, 6);
  }
}

function toggleComparison(personId) {
  if (state.comparisonIds.includes(personId)) {
    state.comparisonIds = state.comparisonIds.filter((id) => id !== personId);
  } else {
    state.comparisonIds = [personId, ...state.comparisonIds].slice(0, 6);
  }
  if (!state.selectedId && state.comparisonIds.length) {
    state.selectedId = state.comparisonIds[0];
  }
  renderExplorer();
}

function selectBranch(branch) {
  state.branch = branch;
  $("branchFilter").value = branch;
  if (branch && branch !== "Legislative") {
    clearCongressionalFilters();
  }
  renderExplorer();
}

function clearCongressionalFilters() {
  state.chamber = "";
  state.congressNumber = "";
  state.party = "";
  state.officialState = "";
  state.district = "";
  for (const id of ["chamberFilter", "congressFilter", "partyFilter", "stateFilter", "districtFilter"]) {
    const control = $(id);
    if (control) control.value = "";
  }
}

function renderSummary() {
  const summary = state.data.summary;
  $("demoNotice").innerHTML = `
    <strong>Data status</strong>
    <span>${escapeHtml(state.data.disclaimer)}</span>
  `;
  $("summaryMetrics").innerHTML = [
    ["Tracked Officials", summary.tracked_public_official_count],
    ["Official Roles", summary.public_official_role_count],
    ["Legislative Roles", summary.public_official_role_counts_by_branch.Legislative || 0],
    ["Executive Roles", summary.public_official_role_counts_by_branch.Executive || 0],
    ["Judicial Roles", summary.public_official_role_counts_by_branch.Judicial || 0],
    ["Demo Filings", summary.filing_count],
    ["Demo Trades", summary.trade_count],
    ["Timeline Trades", summary.career_timeline_trade_count || 0],
    ["Market Price Points", summary.market_price_point_count || 0],
  ]
    .map(
      ([label, value]) => `
        <div class="metric">
          <strong>${fmt.format(value)}</strong>
          <span>${label}</span>
        </div>
      `
    )
    .join("");
  $("footerVersion").textContent = `Dataset ${state.data.dataset_version} / generated ${state.data.generated_at}`;
  const readout = $("datasetReadout");
  if (readout) readout.textContent = state.data.dataset_version;
}

function renderBranchChart() {
  const counts = branchPeopleCounts();
  const max = Math.max(...Object.values(counts), 1);
  $("branchChart").innerHTML = `
    <svg viewBox="0 0 760 280" role="img" aria-label="Official count by branch">
      <rect x="0" y="0" width="760" height="280" fill="transparent"></rect>
      ${branchOrder
        .map((branch, index) => {
          const count = counts[branch] || 0;
          const y = 46 + index * 70;
          const width = count ? 520 * (count / max) : 4;
          const color = branchColors[branch] || "#0f766e";
          return `
            <text x="28" y="${y}" fill="#17201d" font-size="18" font-weight="800">${branch}</text>
            <rect x="170" y="${y - 16}" width="530" height="26" rx="6" fill="#edf4ef"></rect>
            <rect x="170" y="${y - 16}" width="${width}" height="26" rx="6" fill="${color}"></rect>
            <text x="${Math.min(708, 184 + width)}" y="${y + 3}" fill="#17201d" font-size="15" font-weight="800">${fmt.format(count)}</text>
          `;
        })
        .join("")}
      <text x="28" y="252" fill="#64706a" font-size="14">Branch overview across source-backed public-official roles.</text>
    </svg>
  `;

  const roleCounts = roleCategoryCounts();
  $("globalRoleBreakdown").innerHTML = Object.entries(roleCounts)
    .sort(([, a], [, b]) => b - a)
    .map(
      ([category, count]) => `
        <div class="mini-stat">
          <strong>${fmt.format(count)}</strong>
          <span>${escapeHtml(roleCategoryLabel(category))}</span>
        </div>
      `
    )
    .join("");

  $("branchCards").innerHTML = branchOrder
    .map(
      (branch) => `
        <button class="branch-card ${state.branch === branch ? "active" : ""}" data-branch-card="${escapeHtml(branch)}">
          <span>${escapeHtml(branch)}</span>
          <strong>${fmt.format(counts[branch] || 0)}</strong>
          <small>${state.branch === branch ? "Filtering" : "Filter branch"}</small>
        </button>
      `
    )
    .join("");

  document.querySelectorAll("[data-branch-card]").forEach((button) => {
    button.addEventListener("click", () => selectBranch(button.getAttribute("data-branch-card")));
  });
}

function hydrateControls() {
  const branches = branchOrder.filter(
    (branch) => branch === "Legislative" || state.explorerPeople.some((person) => person.branch === branch)
  );
  $("branchFilter").innerHTML =
    '<option value="">All branches</option>' +
    branches.map((branch) => `<option value="${branch}">${branch}</option>`).join("");

  $("roleFilter").innerHTML =
    '<option value="">All role types</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.role_category))]
      .sort()
      .map(
        (category) =>
          `<option value="${escapeHtml(category)}">${escapeHtml(roleCategoryLabel(category))}</option>`
      )
      .join("");

  const terms = Object.entries(state.data.public_officials.scope.presidential_terms);
  $("termFilter").innerHTML =
    '<option value="">All terms</option>' +
    terms.map(([id, term]) => `<option value="${id}">${escapeHtml(term.label)}</option>`).join("");

  $("chamberFilter").innerHTML =
    '<option value="">All chambers</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.source_metadata?.chamber).filter(Boolean))]
      .sort()
      .map((chamber) => `<option value="${escapeHtml(chamber)}">${escapeHtml(chamber)}</option>`)
      .join("");

  $("congressFilter").innerHTML =
    '<option value="">All Congresses</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.source_metadata?.congress_number).filter(Boolean))]
      .sort((a, b) => Number(a) - Number(b))
      .map((congress) => `<option value="${escapeHtml(congress)}">${escapeHtml(congress)}th Congress</option>`)
      .join("");

  $("partyFilter").innerHTML =
    '<option value="">All parties</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.source_metadata?.party).filter(Boolean))]
      .sort()
      .map((party) => `<option value="${escapeHtml(party)}">${escapeHtml(party)}</option>`)
      .join("");

  $("stateFilter").innerHTML =
    '<option value="">All states</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.source_metadata?.state).filter(Boolean))]
      .sort()
      .map((officialState) => `<option value="${escapeHtml(officialState)}">${escapeHtml(officialState)}</option>`)
      .join("");

  $("districtFilter").innerHTML =
    '<option value="">All districts</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.source_metadata?.district).filter(Boolean))]
      .sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }))
      .map((district) => `<option value="${escapeHtml(district)}">${escapeHtml(district)}</option>`)
      .join("");

  const timeline = state.data.career_trade_timeline || {};
  $("timelineAssetFilter").innerHTML =
    '<option value="">All asset classes</option>' +
    (timeline.asset_classes || [])
      .map((assetClass) => `<option value="${escapeHtml(assetClass)}">${escapeHtml(roleCategoryLabel(assetClass))}</option>`)
      .join("");
  $("timelineEventFilter").innerHTML =
    '<option value="">All event types</option>' +
    (timeline.event_types || [])
      .map((eventType) => `<option value="${escapeHtml(eventType)}">${escapeHtml(roleCategoryLabel(eventType))}</option>`)
      .join("");
  $("timelineZoomFilter").innerHTML =
    (timeline.zoom_presets || [{ id: "full", label: "Full career" }])
      .map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`)
      .join("");

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderExplorer();
  });
  $("branchFilter").addEventListener("change", (event) => {
    state.branch = event.target.value;
    if (state.branch && state.branch !== "Legislative") {
      clearCongressionalFilters();
    }
    renderExplorer();
  });
  $("roleFilter").addEventListener("change", (event) => {
    state.roleCategory = event.target.value;
    renderExplorer();
  });
  $("termFilter").addEventListener("change", (event) => {
    state.term = event.target.value;
    renderExplorer();
  });
  $("chamberFilter").addEventListener("change", (event) => {
    state.chamber = event.target.value;
    renderExplorer();
  });
  $("congressFilter").addEventListener("change", (event) => {
    state.congressNumber = event.target.value;
    renderExplorer();
  });
  $("partyFilter").addEventListener("change", (event) => {
    state.party = event.target.value;
    renderExplorer();
  });
  $("stateFilter").addEventListener("change", (event) => {
    state.officialState = event.target.value;
    renderExplorer();
  });
  $("districtFilter").addEventListener("change", (event) => {
    state.district = event.target.value;
    renderExplorer();
  });
  $("clearFilters").addEventListener("click", () => {
    state.query = "";
    state.branch = "";
    state.roleCategory = "";
    state.term = "";
    clearCongressionalFilters();
    $("searchInput").value = "";
    $("branchFilter").value = "";
    $("roleFilter").value = "";
    $("termFilter").value = "";
    renderExplorer();
  });
  $("careerAxisButton").addEventListener("click", () => {
    state.timelineAxis = "career";
    renderCareerTimeline();
  });
  $("calendarAxisButton").addEventListener("click", () => {
    state.timelineAxis = "calendar";
    renderCareerTimeline();
  });
  $("eventWindowAxisButton").addEventListener("click", () => {
    state.timelineAxis = "event_window";
    state.timelineZoom = "event-window";
    $("timelineZoomFilter").value = "event-window";
    renderCareerTimeline();
  });
  $("timelineZoomFilter").addEventListener("change", (event) => {
    state.timelineZoom = event.target.value;
    renderCareerTimeline();
  });
  $("timelineOfficialSearch").addEventListener("input", (event) => {
    state.timelineOfficialQuery = event.target.value;
    renderCareerTimeline();
  });
  $("timelineAssetFilter").addEventListener("change", (event) => {
    state.timelineAssetClass = event.target.value;
    renderCareerTimeline();
  });
  $("timelineOverlayFilter").addEventListener("change", (event) => {
    state.timelineOverlay = event.target.value;
    renderCareerTimeline();
  });
  $("timelineEventFilter").addEventListener("change", (event) => {
    state.timelineEventType = event.target.value;
    renderCareerTimeline();
  });
  $("presidentBaselineButton").addEventListener("click", () => {
    const defaultIds = state.data.career_trade_timeline?.default_official_ids || [];
    state.comparisonIds = defaultIds.length ? defaultIds : state.comparisonIds;
    state.selectedId = state.comparisonIds[0] || state.selectedId;
    renderExplorer();
  });
}

function renderPeopleList(people) {
  const directoryCount = $("directoryCount");
  const limit = 120;
  const shown = people.slice(0, limit);
  directoryCount.textContent = `${fmt.format(people.length)} match${people.length === 1 ? "" : "es"}`;
  $("directoryHint").textContent =
    people.length > limit ? `Showing first ${fmt.format(limit)}. Refine search to narrow.` : "Select officials to compare.";
  $("peopleList").innerHTML =
    shown
      .map((person) => {
        const compared = state.comparisonIds.includes(person.id);
        return `
          <article class="person-row ${person.id === state.selectedId ? "active" : ""}">
            <button class="person-button" data-person-id="${escapeHtml(person.id)}">
              <strong>${escapeHtml(person.full_name)}</strong>
              <span>${escapeHtml(affiliation(person))}</span>
              <small>${fmt.format(person.roles.length)} role${person.roles.length === 1 ? "" : "s"}</small>
            </button>
            <button class="compare-toggle ${compared ? "active" : ""}" data-compare-id="${escapeHtml(person.id)}">
              ${compared ? "Remove" : "Compare"}
            </button>
          </article>
        `;
      })
      .join("") || '<p class="muted">No matching officials.</p>';

  document.querySelectorAll("[data-person-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.getAttribute("data-person-id");
      ensureComparisonHas(state.selectedId);
      renderExplorer();
    });
  });
  document.querySelectorAll("[data-compare-id]").forEach((button) => {
    button.addEventListener("click", () => toggleComparison(button.getAttribute("data-compare-id")));
  });
}

function graphExtent(people) {
  const years = people
    .flatMap((person) =>
      person.roles.flatMap((role) => [role.service_start, role.service_end].filter(Boolean))
    )
    .map((value) => Number(value.slice(0, 4)))
    .filter(Boolean);
  const currentYear = new Date().getFullYear();
  return {
    minYear: Math.min(2017, ...years),
    maxYear: Math.max(currentYear, ...years),
  };
}

function comparisonGraphSvg(people) {
  const lanes = people.length ? people : state.explorerPeople.slice(0, 3);
  const width = 980;
  const laneHeight = 72;
  const height = 92 + lanes.length * laneHeight;
  const left = 180;
  const right = 36;
  const { minYear, maxYear } = graphExtent(lanes);
  const yearSpan = Math.max(1, maxYear - minYear + 1);
  const xFor = (value) => {
    const year = value ? Number(value.slice(0, 4)) : maxYear;
    return left + ((year - minYear) / yearSpan) * (width - left - right);
  };

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Selected official role comparison">
      <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
      ${Array.from({ length: maxYear - minYear + 1 }, (_, index) => minYear + index)
        .map((year) => {
          const x = left + ((year - minYear) / yearSpan) * (width - left - right);
          return `
            <line x1="${x}" y1="44" x2="${x}" y2="${height - 34}" stroke="#d9e0e6" stroke-width="1"></line>
            <text x="${x - 12}" y="${height - 12}" fill="#64706a" font-size="12">${year}</text>
          `;
        })
        .join("")}
      ${lanes
        .map((person, index) => {
          const y = 64 + index * laneHeight;
          const color = branchColors[person.branch] || "#0f766e";
          return `
            <text x="24" y="${y - 8}" fill="#17201d" font-size="14" font-weight="800">${escapeHtml(person.full_name)}</text>
            <text x="24" y="${y + 12}" fill="#64706a" font-size="12">${escapeHtml(person.branch)}</text>
            <line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="#edf4ef" stroke-width="10" stroke-linecap="round"></line>
            ${person.roles
              .map((role) => {
                const x1 = xFor(role.service_start);
                const x2 = Math.max(x1 + 18, xFor(role.service_end));
                return `
                  <line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${color}" stroke-width="9" stroke-linecap="round">
                    <title>${escapeHtml(`${person.full_name}: ${role.role_title}`)}</title>
                  </line>
                  <circle cx="${x1}" cy="${y}" r="5" fill="${color}"></circle>
                `;
              })
              .join("")}
          `;
        })
        .join("")}
    </svg>
  `;
}

function timelineOfficialsById() {
  return new Map((state.data.career_trade_timeline?.officials || []).map((official) => [official.id, official]));
}

function timelinePlaceholderOfficial(person) {
  const starts = person.roles.map((role) => role.service_start).filter(Boolean).sort();
  const ends = person.roles.map((role) => role.service_end).filter(Boolean).sort();
  const active = person.roles.some((role) => role.service_start && !role.service_end);
  return {
    id: person.id,
    full_name: person.full_name,
    branch: person.branch,
    timeline_group: "source_backed_no_trades",
    service_start: starts[0] || null,
    service_end: active ? new Date().toISOString().slice(0, 10) : ends.at(-1) || starts[0] || null,
    roles: person.roles,
    trades: [],
    events: [],
    stats: {
      trade_count: 0,
      buy_count: 0,
      sell_count: 0,
      crypto_count: 0,
      total_value_midpoint: 0,
      disclosure_status: "No reviewed trade disclosures ingested yet",
    },
  };
}

function selectedTimelineOfficials() {
  const timelineById = timelineOfficialsById();
  const explorerById = new Map(state.explorerPeople.map((person) => [person.id, person]));
  const selectedIds = state.comparisonIds.length
    ? state.comparisonIds
    : state.data.career_trade_timeline?.default_official_ids || [];
  const rows = selectedIds
    .map((id) => timelineById.get(id) || (explorerById.get(id) ? timelinePlaceholderOfficial(explorerById.get(id)) : null))
    .filter(Boolean)
    .slice(0, 6);
  const timelineQuery = state.timelineOfficialQuery.trim().toLowerCase();
  if (!timelineQuery) return rows;
  const existing = new Set(rows.map((official) => official.id));
  const timelineMatches = (state.data.career_trade_timeline?.officials || [])
    .filter(
      (official) =>
        !existing.has(official.id) &&
        [official.full_name, official.branch, official.timeline_group]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(timelineQuery)
    );
  for (const official of timelineMatches) existing.add(official.id);
  const explorerMatches = state.explorerPeople
    .filter((person) => !existing.has(person.id) && personMatchesQuery(person, timelineQuery))
    .slice(0, Math.max(0, 6 - rows.length))
    .map((person) => timelineById.get(person.id) || timelinePlaceholderOfficial(person));
  return rows.concat(timelineMatches, explorerMatches).slice(0, 6);
}

function timelineTradeVisible(trade) {
  return !state.timelineAssetClass || trade.asset_class === state.timelineAssetClass;
}

function timelineEventVisible(event) {
  return !state.timelineEventType || event.event_type === state.timelineEventType;
}

function dateToDay(value) {
  if (!value) return null;
  return Math.round(new Date(`${value}T00:00:00`).getTime() / 86400000);
}

function timelineExtent(officials) {
  const values = [];
  const zoomPreset = (state.data.career_trade_timeline?.zoom_presets || []).find((preset) => preset.id === state.timelineZoom);
  for (const official of officials) {
    if (state.timelineAxis !== "calendar") {
      values.push(0);
      values.push(dateToDay(official.service_end) - dateToDay(official.service_start));
      for (const trade of official.trades.filter(timelineTradeVisible)) values.push(trade.career_day);
      for (const event of (official.events || []).filter(timelineEventVisible)) values.push(event.career_day);
    } else {
      values.push(dateToDay(official.service_start));
      values.push(dateToDay(official.service_end));
      for (const trade of official.trades.filter(timelineTradeVisible)) values.push(dateToDay(trade.date));
      for (const event of (official.events || []).filter(timelineEventVisible)) values.push(dateToDay(event.date));
    }
  }
  const clean = values.filter((value) => Number.isFinite(value));
  if (state.timelineAxis !== "calendar" && zoomPreset?.days) {
    if (state.timelineAxis === "event_window" && state.activeTimelineEventId) {
      const eventDays = officials
        .flatMap((official) => (official.events || []).filter((event) => event.id === state.activeTimelineEventId))
        .map((event) => event.career_day)
        .filter((value) => Number.isFinite(value));
      if (eventDays.length) {
        const center = eventDays[0];
        return { min: center - 180, max: center + 180 };
      }
    }
    return { min: 0, max: zoomPreset.days };
  }
  return {
    min: Math.min(...clean, 0),
    max: Math.max(...clean, 1),
  };
}

function timelineTickLabel(value, extent) {
  if (state.timelineAxis !== "calendar") {
    const years = Math.round(value / 365);
    return years <= 0 ? "Start" : `Y${years}`;
  }
  const date = new Date(value * 86400000);
  return String(date.getUTCFullYear());
}

function timelineEventById(eventId) {
  for (const official of state.data.career_trade_timeline?.officials || []) {
    const found = (official.events || []).find((event) => event.id === eventId);
    if (found) return found;
  }
  return (state.data.career_trade_timeline?.events || []).find((event) => event.id === eventId) || null;
}

function selectedEventRelatedTrades(event) {
  if (!event) return [];
  const eventDay = dateToDay(event.date);
  return selectedTimelineOfficials()
    .flatMap((official) =>
      (official.trades || [])
        .filter((trade) => Math.abs(dateToDay(trade.date) - eventDay) <= (event.window_days || 180))
        .map((trade) => ({
          official: official.full_name,
          ...trade,
          days_from_event: dateToDay(trade.date) - eventDay,
        }))
    )
    .sort((a, b) => Math.abs(a.days_from_event) - Math.abs(b.days_from_event))
    .slice(0, 12);
}

function sourceLinks(event) {
  return (event?.source_urls || [])
    .map(
      (url, index) =>
        `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1}</a>`
    )
    .join("");
}

function careerTimelineSvg(officials) {
  const width = 1120;
  const laneHeight = 104;
  const height = 112 + Math.max(1, officials.length) * laneHeight;
  const left = 190;
  const right = 42;
  const extent = timelineExtent(officials);
  const span = Math.max(1, extent.max - extent.min);
  const xFor = (value) => left + ((value - extent.min) / span) * (width - left - right);
  const ticks = Array.from({ length: 6 }, (_, index) => extent.min + (span / 5) * index);

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Career trade timeline">
      <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
      ${ticks
        .map((tick) => {
          const x = xFor(tick);
          return `
            <line x1="${x}" y1="48" x2="${x}" y2="${height - 44}" stroke="#dbe4e0"></line>
            <text x="${x - 16}" y="${height - 16}" fill="#64706a" font-size="12">${escapeHtml(timelineTickLabel(tick, extent))}</text>
          `;
        })
        .join("")}
      ${officials
        .map((official, index) => {
          const y = 74 + index * laneHeight;
          const color = branchColors[official.branch] || "#0b6b8f";
          const startValue = state.timelineAxis !== "calendar" ? 0 : dateToDay(official.service_start);
          const endValue =
            state.timelineAxis !== "calendar"
              ? dateToDay(official.service_end) - dateToDay(official.service_start)
              : dateToDay(official.service_end);
          const visibleTrades = (official.trades || []).filter(timelineTradeVisible);
          const visibleEvents = (official.events || []).filter(timelineEventVisible);
          const visibleClusters = (official.trade_clusters || []).filter((cluster) =>
            visibleTrades.some((trade) => trade.date >= cluster.start_date && trade.date <= cluster.end_date)
          );
          const sourceStatuses = (official.disclosure_sources || [])
            .map((source) => source.source_status)
            .filter(Boolean)
            .join(" / ");
          return `
            <text x="24" y="${y - 22}" fill="#17201d" font-size="14" font-weight="800">${escapeHtml(official.full_name)}</text>
            <text x="24" y="${y - 4}" fill="#64706a" font-size="12">${escapeHtml(official.stats?.disclosure_status || official.branch)}</text>
            <text x="24" y="${y + 14}" fill="#8a5a12" font-size="11">${escapeHtml(official.stats?.confidence_label || sourceStatuses || "Source status pending")}</text>
            <line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="#edf4ef" stroke-width="12" stroke-linecap="round"></line>
            ${
              Number.isFinite(startValue) && Number.isFinite(endValue)
                ? `<line x1="${xFor(startValue)}" y1="${y}" x2="${xFor(Math.max(endValue, startValue + 1))}" y2="${y}" stroke="${color}" stroke-width="7" stroke-linecap="round"></line>`
                : ""
            }
            ${
              visibleTrades.length
                ? visibleTrades
                    .map((trade) => {
                      const value = state.timelineAxis !== "calendar" ? trade.career_day : dateToDay(trade.date);
                      if (!Number.isFinite(value)) return "";
                      const radius = Math.max(5, Math.min(14, Math.sqrt((trade.value_midpoint || 0) / 5000)));
                      const fill = trade.asset_class === "crypto" ? "#b66a1d" : trade.action === "SELL" ? "#9f3a3a" : "#0b6b8f";
                      const showPrice = state.timelineOverlay !== "hide-prices" && (state.timelineOverlay !== "crypto" || trade.asset_class === "crypto");
                      const priceLabel = showPrice && trade.price_window?.closest_close ? ` / close ${trade.price_window.closest_close}` : "";
                      return `
                        <circle cx="${xFor(value)}" cy="${y}" r="${radius.toFixed(1)}" fill="${fill}" stroke="#fff" stroke-width="2">
                          <title>${escapeHtml(`${official.full_name}: ${trade.action} ${trade.ticker} ${trade.value_range_label} on ${shortDate(trade.date)}${priceLabel} / ${trade.confidence_label || official.stats?.confidence_label || "confidence pending"}`)}</title>
                        </circle>
                      `;
                    })
                    .join("")
                : `<text x="${left}" y="${y + 28}" fill="#64706a" font-size="12">No reviewed trade rows in this snapshot</text>`
            }
            ${visibleClusters
              .map((cluster) => {
                const clusterValue =
                  state.timelineAxis !== "calendar"
                    ? dateToDay(cluster.start_date) - dateToDay(official.service_start)
                    : dateToDay(cluster.start_date);
                if (!Number.isFinite(clusterValue)) return "";
                const x = xFor(clusterValue);
                return `
                  <g>
                    <rect x="${x - 24}" y="${y + 20}" width="48" height="18" rx="6" fill="#17212b">
                      <title>${escapeHtml(`${cluster.trade_count} trades from ${shortDate(cluster.start_date)} to ${shortDate(cluster.end_date)}: ${cluster.tickers.join(", ")}`)}</title>
                    </rect>
                    <text x="${x - 18}" y="${y + 33}" fill="#ffffff" font-size="11" font-weight="800">${cluster.trade_count} trades</text>
                  </g>
                `;
              })
              .join("")}
            ${visibleEvents
              .map((event) => {
                const value = state.timelineAxis !== "calendar" ? event.career_day : dateToDay(event.date);
                if (!Number.isFinite(value)) return "";
                const x = xFor(value);
                return `
                  <rect x="${x - 5}" y="${y - 36}" width="10" height="10" transform="rotate(45 ${x} ${y - 31})" fill="#7154a6" data-timeline-event="${escapeHtml(event.id)}">
                    <title>${escapeHtml(`${event.label}: ${event.description}`)}</title>
                  </rect>
                `;
              })
              .join("")}
          `;
        })
        .join("")}
    </svg>
  `;
}

function renderTimelineEventDetail() {
  const event = state.activeTimelineEventId ? timelineEventById(state.activeTimelineEventId) : null;
  const relatedTrades = selectedEventRelatedTrades(event);
  $("timelineEventDetail").innerHTML = event
    ? `
      <div>
        <p class="eyebrow">${escapeHtml(roleCategoryLabel(event.event_type))} / ${shortDate(event.date)}</p>
        <h3>${escapeHtml(event.label)}</h3>
        <p>${escapeHtml(event.description || "No event description available.")}</p>
        <small>${escapeHtml(event.source || "CivicLedger event context")} / ${escapeHtml(event.relevance || "general")} / relevance ${fmt.format(event.relevance_score || 0)}</small>
        <p>${escapeHtml(event.relevance_reason || "General public context")}</p>
        <div class="event-detail-links">${sourceLinks(event) || '<span class="muted">No source link recorded.</span>'}</div>
        <div class="event-related-trades">
          <strong>Related selected-lane trades</strong>
          ${
            relatedTrades.length
              ? relatedTrades
                  .map(
                    (trade) =>
                      `<span>${escapeHtml(trade.official)}: ${escapeHtml(trade.action)} ${escapeHtml(trade.ticker || trade.asset_display_name)} ${escapeHtml(trade.value_range_label)} (${trade.days_from_event > 0 ? "+" : ""}${fmt.format(trade.days_from_event)}d)</span>`
                  )
                  .join("")
              : '<span>No selected-lane trades within this event window.</span>'
          }
        </div>
      </div>
    `
    : `
      <div>
        <p class="eyebrow">Event detail</p>
        <h3>Select an event marker</h3>
        <p>Event markers open here with a concise source-aware summary while the chart stays in view.</p>
      </div>
    `;
}

function renderCareerTimeline() {
  const timeline = state.data.career_trade_timeline || {};
  const officials = selectedTimelineOfficials();
  $("careerAxisButton").classList.toggle("active", state.timelineAxis === "career");
  $("calendarAxisButton").classList.toggle("active", state.timelineAxis === "calendar");
  $("eventWindowAxisButton").classList.toggle("active", state.timelineAxis === "event_window");
  $("careerTimelineSummary").innerHTML = [
    ["Baseline Officials", timeline.summary?.default_official_count || 0],
    ["Compared Lanes", officials.length],
    ["Timeline Trades", officials.reduce((total, official) => total + (official.trades || []).filter(timelineTradeVisible).length, 0)],
    ["Crypto Trades", officials.reduce((total, official) => total + (official.trades || []).filter((trade) => timelineTradeVisible(trade) && trade.asset_class === "crypto").length, 0)],
    ["Clusters", officials.reduce((total, official) => total + (official.trade_clusters || []).length, 0)],
    ["Event Markers", officials.reduce((total, official) => total + (official.events || []).filter(timelineEventVisible).length, 0)],
  ]
    .map(
      ([label, value]) => `
        <div class="mini-stat">
          <strong>${fmt.format(value)}</strong>
          <span>${escapeHtml(label)}</span>
        </div>
      `
    )
    .join("");
  $("careerTimelineChart").innerHTML = officials.length
    ? careerTimelineSvg(officials)
    : '<p class="muted">Select officials to build a timeline.</p>';
  document.querySelectorAll("[data-timeline-event]").forEach((marker) => {
    marker.addEventListener("click", () => {
      state.activeTimelineEventId = marker.getAttribute("data-timeline-event");
      renderTimelineEventDetail();
    });
  });
  renderTimelineEventDetail();
}

function renderSelectedChips(people) {
  $("selectedChips").innerHTML =
    people
      .map(
        (person) => `
          <button class="selected-chip" data-remove-compare="${escapeHtml(person.id)}">
            <span>${escapeHtml(person.full_name)}</span>
            <small>${escapeHtml(person.branch)}</small>
          </button>
        `
      )
      .join("") || '<span class="muted">Select officials from the results list to overlay them.</span>';

  document.querySelectorAll("[data-remove-compare]").forEach((button) => {
    button.addEventListener("click", () => toggleComparison(button.getAttribute("data-remove-compare")));
  });
}

function renderComparison() {
  const compared = peopleByIds(state.comparisonIds);
  renderSelectedChips(compared);
  $("comparisonGraph").innerHTML = comparisonGraphSvg(compared);
  $("comparisonCount").textContent = `${fmt.format(compared.length)} selected`;
}

function renderProfile(person) {
  const latestRole = person.primary_role;
  $("profilePanel").innerHTML = `
    <div class="profile-header">
      <div>
        <p class="eyebrow">${escapeHtml(person.branch)}</p>
        <h2>${escapeHtml(person.full_name)}</h2>
        <p>${escapeHtml(affiliation(person))}</p>
      </div>
      <span class="badge gold">${fmt.format(person.roles.length)} role${person.roles.length === 1 ? "" : "s"}</span>
    </div>

    <div class="profile-grid">
      <div class="mini-stat"><strong>${escapeHtml(latestRole ? termLabel(latestRole.presidential_term) : "n/a")}</strong><span>Latest term</span></div>
      <div class="mini-stat"><strong>${escapeHtml(roleCategoryLabel(latestRole?.role_category || "n/a"))}</strong><span>Role type</span></div>
      <div class="mini-stat"><strong>${escapeHtml(latestRole?.source_metadata?.chamber || latestRole?.source_metadata?.congress_number || "n/a")}</strong><span>Chamber / congress</span></div>
      <div class="mini-stat"><strong>${shortDate(latestRole?.service_start)}</strong><span>Latest start</span></div>
      <div class="mini-stat"><strong>${escapeHtml(latestRole?.source_tier || "n/a")}</strong><span>Source tier</span></div>
    </div>

    <div class="chart-shell">
      <div class="chart-title"><span>Role Records</span><span>Source-backed official data</span></div>
      <table class="trade-table role-table">
        <thead>
          <tr>
            <th>Term</th>
            <th>Chamber</th>
            <th>Role</th>
            <th>Agency / Court</th>
            <th>Start</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          ${person.roles
            .map(
              (role) => `
                <tr>
                  <td>${escapeHtml(termLabel(role.presidential_term))}</td>
                  <td>${escapeHtml(compact([
                    role.source_metadata?.chamber,
                    role.source_metadata?.congress_number ? `${role.source_metadata.congress_number}th` : null,
                    role.source_metadata?.state,
                    role.source_metadata?.district,
                  ]) || "n/a")}</td>
                  <td>${escapeHtml(role.role_title)}</td>
                  <td>${escapeHtml(role.court || role.agency || role.administration)}</td>
                  <td>${shortDate(role.service_start)}</td>
                  <td><a href="${escapeHtml(role.source_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(role.source_tier)}</a></td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderExplorer() {
  renderBranchChart();
  const people = filteredPeople();
  if (!people.length) {
    renderPeopleList(people);
    renderComparison();
    renderCareerTimeline();
    $("profilePanel").innerHTML = `
      <div class="empty-state">
        <h3>No officials match these filters</h3>
        <p>Clear filters or choose another branch, term, role type, or search query.</p>
      </div>
    `;
    return;
  }
  if (!people.some((person) => person.id === state.selectedId)) {
    state.selectedId = people[0].id;
  }
  ensureComparisonHas(state.selectedId);
  renderPeopleList(people);
  renderComparison();
  renderCareerTimeline();
  const selected = state.explorerPeople.find((person) => person.id === state.selectedId);
  if (selected) renderProfile(selected);
}

function renderSources() {
  $("sourceGrid").innerHTML = state.data.sources
    .map(
      (source) => `
        <article class="source-card">
          <div class="profile-header">
            <div>
              <h3>${escapeHtml(source.name)}</h3>
              <p>${escapeHtml(source.records_scope)}</p>
            </div>
            <span class="badge">${escapeHtml(source.branch)}</span>
          </div>
          <div class="source-meta">
            <span class="badge">${fmt.format(source.fixture_counts.raw_documents)} raw docs</span>
            <span class="badge">${fmt.format(source.fixture_counts.filings)} filings</span>
            <span class="badge">${fmt.format(source.fixture_counts.trades)} trades</span>
            <span class="badge gold">${escapeHtml(source.readiness.status)}</span>
          </div>
          <p><strong>Access mode:</strong> ${escapeHtml(source.access_mode)}</p>
          <p><strong>Readiness:</strong> ${escapeHtml(source.readiness.label)}</p>
          <p><strong>Missing:</strong> ${escapeHtml((source.readiness.missing_capabilities || []).join(" / ") || "n/a")}</p>
          <p><a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">Official source</a></p>
        </article>
      `
    )
    .join("");
}

function renderCompleteness() {
  const dashboard = state.data.disclosure_pipeline?.completeness_dashboard || {};
  const summary = dashboard.summary || {};
  const branches = dashboard.branches || [];
  const rows = dashboard.rows || [];
  const batches = state.data.disclosure_pipeline?.retrieval_batches?.batches || [];
  const alerts = state.data.disclosure_pipeline?.source_staleness_alerts?.alerts || [];
  const production = state.data.disclosure_pipeline?.production_promotions || {};
  $("completenessSummary").innerHTML = [
    ["Queue Items", summary.queue_item_count || 0],
    ["Retrieval Batches", summary.retrieval_batch_count || 0],
    ["Batch Candidates", summary.retrieval_candidate_count || 0],
    ["Raw Documents", summary.archived_raw_document_count || 0],
    ["Reviewed Fixtures", summary.reviewed_fixture_promotion_count || 0],
    ["Public Trade Rows", summary.reviewed_public_trade_count || 0],
    ["Open Alerts", summary.open_warning_count || 0],
  ]
    .map(
      ([label, value]) => `
        <div class="mini-stat">
          <strong>${fmt.format(value)}</strong>
          <span>${escapeHtml(label)}</span>
        </div>
      `
    )
    .join("");

  $("completenessGrid").innerHTML =
    branches
      .map((branch) => {
        const branchClass = String(branch.branch || "").toLowerCase();
        return `
          <article class="completeness-card ${escapeHtml(branchClass)}">
            <span>${escapeHtml(branch.branch)}</span>
            <strong>${fmt.format(branch.queue_item_count || 0)} queued</strong>
            <small>${fmt.format(branch.official_count || 0)} officials / ${fmt.format(branch.role_count || 0)} roles</small>
            <small>${fmt.format(branch.archived_raw_document_count || 0)} raw docs / ${fmt.format(branch.reviewed_public_trade_count || 0)} reviewed public trades</small>
            <small>${fmt.format(branch.retrieval_candidate_count || 0)} batch candidates / ${fmt.format(branch.open_alert_count || 0)} alerts</small>
            <span class="readiness-chip ${escapeHtml(branch.readiness_status || "")}">${escapeHtml(roleCategoryLabel(branch.readiness_status || "pending"))}</span>
          </article>
        `;
      })
      .join("") || '<p class="muted">No completeness dashboard rows generated yet.</p>';

  $("completenessCount").textContent = `${fmt.format(rows.length)} rows`;
  $("completenessRows").innerHTML =
    rows
      .slice(0, 96)
      .map(
        (row) => {
          const taskKey = `${row.source_id}|${row.presidential_term}`;
          return `
          <tr>
            <td>
              <strong>${escapeHtml(row.branch)}</strong>
              <small>${escapeHtml(termLabel(row.presidential_term))}</small>
            </td>
            <td>${escapeHtml(row.source_id)}</td>
            <td>${fmt.format(row.official_count || 0)} officials<br /><small>${fmt.format(row.role_count || 0)} roles</small></td>
            <td>${fmt.format(row.queue_item_count || 0)}<br /><small>${fmt.format(row.current_queue_item_count || 0)} current</small></td>
            <td>${fmt.format(row.archived_raw_document_count || 0)}</td>
            <td>${fmt.format(row.reviewed_public_trade_count || 0)}</td>
            <td><span class="readiness-chip ${escapeHtml(row.readiness_status || "")}">${escapeHtml(roleCategoryLabel(row.readiness_status || "pending"))}</span></td>
            <td><button class="row-action" data-source-task="${escapeHtml(taskKey)}">Details</button></td>
          </tr>
        `;
        }
      )
      .join("");

  function renderTask(row) {
    const batch = batches.find((item) => item.source_id === row.source_id);
    const sourceAlerts = alerts.filter((item) => !item.source_id || item.source_id === row.source_id);
    const candidates = (batch?.candidates || []).slice(0, 6);
    $("sourceTaskDetail").innerHTML = `
      <div>
        <p class="eyebrow">Source task detail</p>
        <h3>${escapeHtml(row.source_id)} / ${escapeHtml(termLabel(row.presidential_term))}</h3>
        <p>${escapeHtml(batch?.instruction || "No retrieval batch generated for this source yet.")}</p>
        <div class="source-task-meta">
          <span class="readiness-chip ${escapeHtml(row.retrieval_batch_status || "")}">${escapeHtml(roleCategoryLabel(row.retrieval_batch_status || "not_batched"))}</span>
          <span>${fmt.format(row.queue_item_count || 0)} queued</span>
          <span>${fmt.format(row.retrieval_candidate_count || 0)} first-pass candidates</span>
          <span>${fmt.format(production.summary?.reviewed_public_trade_count || 0)} reviewed public trades</span>
        </div>
        <div class="task-columns">
          <div>
            <strong>First candidates</strong>
            ${
              candidates.length
                ? candidates
                    .map(
                      (candidate) =>
                        `<p>${escapeHtml(candidate.full_name)} <small>${escapeHtml(compact([
                          candidate.chamber,
                          candidate.congress_number ? `${candidate.congress_number}th Congress` : null,
                          candidate.state,
                          candidate.court,
                          candidate.agency,
                        ]))}</small></p>`
                    )
                    .join("")
                : '<p class="muted">No candidates available.</p>'
            }
          </div>
          <div>
            <strong>Open alerts</strong>
            ${
              sourceAlerts.length
                ? sourceAlerts
                    .map((alert) => `<p>${escapeHtml(alert.severity)}: ${escapeHtml(alert.message)}</p>`)
                    .join("")
                : '<p class="muted">No open source alerts.</p>'
            }
          </div>
        </div>
      </div>
    `;
  }

  const defaultRow = rows.find((row) => row.source_id === "house-financial-disclosure") || rows[0];
  if (defaultRow) renderTask(defaultRow);
  document.querySelectorAll("[data-source-task]").forEach((button) => {
    button.addEventListener("click", () => {
      const [sourceId, termId] = button.getAttribute("data-source-task").split("|");
      const row = rows.find((item) => item.source_id === sourceId && item.presidential_term === termId);
      if (row) renderTask(row);
    });
  });
}

function renderEvents() {
  $("eventsList").innerHTML = state.data.events
    .map(
      (event) => `
        <article class="event-card">
          <div class="event-date">${shortDate(event.date)}</div>
          <div>
            <h3>${escapeHtml(event.label)}</h3>
            <p>${escapeHtml(event.description)}</p>
          </div>
        </article>
      `
    )
    .join("");
}

function renderTradeContext() {
  const fred = state.data.fred_context || {};
  const series = fred.series || {};
  const market = state.data.market || {};
  const marketSummary = market.summary || {};
  const generatedAt = state.data.generated_at || "";
  const coveredSymbols = marketSummary.covered_symbol_count ?? marketSummary.series_count ?? 0;
  const missingSymbols = marketSummary.missing_symbol_count ?? 0;
  const anomalyCount = marketSummary.anomaly_count ?? (market.anomaly_report || []).length;
  const macroIds = ["FEDFUNDS", "CPIAUCSL", "DGS10", "DGS2", "USREC"];
  const marketFreshnessCard = `
    <article class="macro-card market-card">
      <span>Market prices</span>
      <strong>${escapeHtml(marketSummary.active_market_price_provider || market.provider || "market")}</strong>
      <small>${fmt.format(marketSummary.price_point_count || 0)} price points / generated ${shortDate(generatedAt)}</small>
      <small>${fmt.format(coveredSymbols)} covered symbols / ${fmt.format(missingSymbols)} missing / ${fmt.format(anomalyCount)} anomalies</small>
    </article>
  `;
  const macroCards = macroIds
    .map((seriesId) => {
      const item = series[seriesId];
      const latest = latestObservation(item);
      if (!item || !latest) return "";
      return `
        <article class="macro-card">
          <span>${escapeHtml(item.category)}</span>
          <strong>${escapeHtml(formatMacroValue(latest.value, item.units))}</strong>
          <small>${escapeHtml(item.label)} / ${shortDate(latest.date)}</small>
        </article>
      `;
    })
    .join("");
  $("macroSummary").innerHTML = marketFreshnessCard + macroCards;

  $("sourcePriority").innerHTML = (fred.source_priorities || [])
    .map(
      (source) => `
        <article class="priority-row ${escapeHtml(source.status)}">
          <strong>${escapeHtml(source.source)}</strong>
          <span>${escapeHtml(source.status)}</span>
          <p>${escapeHtml(source.reason)}</p>
        </article>
      `
    )
    .join("");

  const rows = state.data.trade_context?.rows || [];
  $("tradeContextCount").textContent = `${fmt.format(rows.length)} demo rows`;
  $("tradeContextRows").innerHTML =
    rows
      .slice(0, 36)
      .map((row) => {
        const assetMoves = moveList(row.horizon_moves?.asset);
        const benchmarkMoves = moveList(row.horizon_moves?.benchmark);
        const reportMoves = (row.trade_to_report_moves || [])
          .map((move) => `${move.symbol}: ${signedPct(move.pct_change)}`)
          .join(" / ");
        const macro = Object.entries(row.macro_snapshot || {})
          .map(([, item]) => `${item.label}: ${formatMacroValue(item.value, item.units)}`)
          .slice(0, 3)
          .join(" / ");
        const events =
          (row.nearby_events || [])
            .map((event) => `${event.label} (${event.days_from_trade > 0 ? "+" : ""}${event.days_from_trade}d)`)
            .slice(0, 2)
            .join(" / ") || "No nearby context events";
        return `
          <tr>
            <td>
              <strong>${escapeHtml(row.person_name)}</strong>
              <small>${escapeHtml(row.market_provider || "market")} prices / ${escapeHtml(row.context_label)}</small>
            </td>
            <td>${shortDate(row.trade_date)}<br /><small>Reported ${shortDate(row.reported_date)} / ${fmt.format(row.disclosure_lag_days)}d lag</small></td>
            <td>
              ${escapeHtml(row.action)} ${escapeHtml(row.ticker || "")}
              <small>${escapeHtml(row.issuer_reference?.issuer_name || row.asset_display_name)}</small>
              <small>${escapeHtml(row.issuer_reference?.sector || "Unmapped")} / benchmark ${escapeHtml(row.issuer_reference?.benchmark_symbol || "SPY")}</small>
              <small>${escapeHtml(row.value_range_label)}</small>
            </td>
            <td>
              <strong>${escapeHtml(row.price_window?.asset?.symbol || row.ticker || "Asset")}</strong>
              <small>7/30/90d ${escapeHtml(assetMoves || "n/a")}</small>
              <small>Trade-report ${escapeHtml(reportMoves || "n/a")}</small>
              ${sparkline(row.price_window?.asset?.points || [], `${row.ticker} price path`)}
              <small>Benchmark ${escapeHtml(row.price_window?.benchmark?.symbol || "SPY")}: ${escapeHtml(benchmarkMoves || "n/a")}</small>
            </td>
            <td>${escapeHtml(macro || "n/a")}</td>
            <td>${escapeHtml(events)}</td>
          </tr>
        `;
      })
      .join("");
}

async function boot() {
  const response = await fetch("./data/civicledger-static.json");
  state.data = await response.json();
  buildExplorerPeople();
  state.comparisonIds = state.data.career_trade_timeline?.default_official_ids?.length
    ? state.data.career_trade_timeline.default_official_ids
    : branchOrder
        .map((branch) => state.explorerPeople.find((person) => person.branch === branch)?.id)
        .filter(Boolean);
  state.selectedId = state.comparisonIds[0] || state.explorerPeople[0]?.id || null;
  renderSummary();
  renderBranchChart();
  hydrateControls();
  renderExplorer();
  renderCompleteness();
  renderSources();
  renderEvents();
  renderTradeContext();
}

boot().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<main class="panel"><h1>CivicLedger</h1><p>Failed to load static demo data.</p></main>`;
});
