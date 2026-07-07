const state = {
  data: null,
  explorerPeople: [],
  selectedId: null,
  comparisonIds: [],
  query: "",
  branch: "",
  roleCategory: "",
  term: "",
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

function affiliation(person) {
  if (!person.primary_role) return person.branch;
  return compact([
    person.branch,
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
    ]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function filteredPeople() {
  const query = state.query.trim().toLowerCase();
  return state.explorerPeople.filter((person) => {
    const branchOk = !state.branch || person.branch === state.branch;
    const roleOk =
      !state.roleCategory || person.roles.some((role) => role.role_category === state.roleCategory);
    const termOk = !state.term || person.roles.some((role) => role.presidential_term === state.term);
    return branchOk && roleOk && termOk && personMatchesQuery(person, query);
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
  renderExplorer();
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
    ["Executive Roles", summary.public_official_role_counts_by_branch.Executive || 0],
    ["Judicial Roles", summary.public_official_role_counts_by_branch.Judicial || 0],
    ["Demo Filings", summary.filing_count],
    ["Demo Trades", summary.trade_count],
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
      <text x="28" y="252" fill="#64706a" font-size="14">Branch overview. Legislative roster ingestion is not populated in this snapshot yet.</text>
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

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderExplorer();
  });
  $("branchFilter").addEventListener("change", (event) => {
    state.branch = event.target.value;
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
  $("clearFilters").addEventListener("click", () => {
    state.query = "";
    state.branch = "";
    state.roleCategory = "";
    state.term = "";
    $("searchInput").value = "";
    $("branchFilter").value = "";
    $("roleFilter").value = "";
    $("termFilter").value = "";
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
      <div class="mini-stat"><strong>${shortDate(latestRole?.service_start)}</strong><span>Latest start</span></div>
      <div class="mini-stat"><strong>${escapeHtml(latestRole?.source_tier || "n/a")}</strong><span>Source tier</span></div>
    </div>

    <div class="chart-shell">
      <div class="chart-title"><span>Role Records</span><span>Source-backed official data</span></div>
      <table class="trade-table role-table">
        <thead>
          <tr>
            <th>Term</th>
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
          </div>
          <p><strong>Access mode:</strong> ${escapeHtml(source.access_mode)}</p>
          <p><strong>Readiness:</strong> ${escapeHtml(source.readiness.label)}</p>
          <p><a href="${escapeHtml(source.source_url)}" target="_blank" rel="noopener noreferrer">Official source</a></p>
        </article>
      `
    )
    .join("");
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

async function boot() {
  const response = await fetch("./data/civicledger-static.json");
  state.data = await response.json();
  buildExplorerPeople();
  state.comparisonIds = branchOrder
    .map((branch) => state.explorerPeople.find((person) => person.branch === branch)?.id)
    .filter(Boolean);
  state.selectedId = state.comparisonIds[0] || state.explorerPeople[0]?.id || null;
  renderSummary();
  renderBranchChart();
  hydrateControls();
  renderExplorer();
  renderSources();
  renderEvents();
}

boot().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<main class="panel"><h1>CivicLedger</h1><p>Failed to load static demo data.</p></main>`;
});
