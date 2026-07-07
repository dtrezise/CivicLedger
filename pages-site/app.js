const state = {
  data: null,
  explorerPeople: [],
  selectedId: null,
  query: "",
  branch: "",
  roleCategory: "",
  officialQuery: "",
  officialBranch: "",
  officialTerm: "",
};

const fmt = new Intl.NumberFormat("en-US");
const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const branchColors = {
  Legislative: "#0b6b8f",
  Executive: "#b66a1d",
  Judicial: "#7154a6",
};

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

function affiliation(person) {
  if (person.primary_role) {
    return compact([
      person.branch,
      termLabel(person.primary_role.presidential_term),
      person.primary_role.office,
      person.primary_role.agency,
      person.primary_role.court,
    ]);
  }
  return compact([
    person.branch,
    person.chamber,
    person.office,
    person.agency,
    person.court,
    person.state,
    person.party,
  ]);
}

function termLabel(termId) {
  return state.data.public_officials?.scope?.presidential_terms?.[termId]?.label || termId;
}

function roleSortValue(role) {
  return role.service_start || "0000-00-00";
}

function branchPeopleCounts() {
  return state.explorerPeople.reduce((counts, person) => {
    counts[person.branch] = (counts[person.branch] || 0) + 1;
    return counts;
  }, {});
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
      const currentRole = roles.find((role) => !role.service_end) || roles[0] || null;
      return {
        id: person.external_person_id,
        full_name: person.full_name,
        branch: person.branch,
        roles,
        primary_role: currentRole,
        trades: [],
        filings: [],
        demo_disclosure_profile: false,
      };
    })
    .sort((a, b) => {
      const branchCompare = a.branch.localeCompare(b.branch);
      return branchCompare || a.full_name.localeCompare(b.full_name);
    });
}

function filteredPeople() {
  const query = state.query.trim().toLowerCase();
  return state.explorerPeople.filter((person) => {
    const branchOk = !state.branch || person.branch === state.branch;
    const roleOk =
      !state.roleCategory ||
      person.roles.some((role) => role.role_category === state.roleCategory);
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
    return branchOk && roleOk && (!query || haystack.includes(query));
  });
}

function renderSummary() {
  const summary = state.data.summary;
  $("demoNotice").innerHTML = `
    <strong>Public demo notice</strong>
    <span>${escapeHtml(state.data.disclaimer)}</span>
  `;
  $("summaryMetrics").innerHTML = [
    ["Demo Disclosure Profiles", summary.official_count],
    ["Tracked Public Officials", summary.tracked_public_official_count],
    ["Official Roles", summary.public_official_role_count],
    ["Filings", summary.filing_count],
    ["Trades", summary.trade_count],
    ["Raw Documents", summary.raw_document_count],
    ["Events", summary.event_count],
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
  const entries = Object.entries(branchPeopleCounts()).sort(([a], [b]) => a.localeCompare(b));
  const max = Math.max(...entries.map(([, count]) => count));
  $("branchChart").innerHTML = `
    <svg viewBox="0 0 520 330" role="img" aria-label="Official count by branch">
      <rect x="0" y="0" width="520" height="330" fill="transparent"></rect>
      ${entries
        .map(([branch, count], index) => {
          const y = 55 + index * 86;
          const width = 340 * (count / max);
          const color = branchColors[branch] || "#0f766e";
          return `
            <text x="24" y="${y}" fill="#17201d" font-size="20" font-weight="800">${branch}</text>
            <rect x="24" y="${y + 18}" width="420" height="28" rx="6" fill="#edf4ef"></rect>
            <rect x="24" y="${y + 18}" width="${width}" height="28" rx="6" fill="${color}"></rect>
            <text x="${Math.min(470, 42 + width)}" y="${y + 39}" fill="#17201d" font-size="17" font-weight="800">${count}</text>
          `;
        })
        .join("")}
      <text x="24" y="296" fill="#64706a" font-size="15">Public-official roster. Disclosure records are still being attached source by source.</text>
    </svg>
  `;
}

function hydrateControls() {
  const branches = [...new Set(state.explorerPeople.map((person) => person.branch))].sort();
  $("branchFilter").innerHTML =
    '<option value="">All branches</option>' +
    branches.map((branch) => `<option value="${branch}">${branch}</option>`).join("");

  $("assetFilter").innerHTML =
    '<option value="">All role types</option>' +
    [...new Set(state.data.public_officials.roles.map((role) => role.role_category))]
      .sort()
      .map(
        (category) =>
          `<option value="${escapeHtml(category)}">${escapeHtml(category.replaceAll("_", " "))}</option>`
      )
      .join("");

  const officialBranches = [
    ...new Set(state.data.public_officials.roles.map((role) => role.branch)),
  ].sort();
  $("officialBranchFilter").innerHTML =
    '<option value="">All branches</option>' +
    officialBranches.map((branch) => `<option value="${branch}">${branch}</option>`).join("");

  const terms = Object.entries(state.data.public_officials.scope.presidential_terms);
  $("officialTermFilter").innerHTML =
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
  $("assetFilter").addEventListener("change", (event) => {
    state.roleCategory = event.target.value;
    renderExplorer();
  });
  $("officialSearchInput").addEventListener("input", (event) => {
    state.officialQuery = event.target.value;
    renderPublicOfficials();
  });
  $("officialBranchFilter").addEventListener("change", (event) => {
    state.officialBranch = event.target.value;
    renderPublicOfficials();
  });
  $("officialTermFilter").addEventListener("change", (event) => {
    state.officialTerm = event.target.value;
    renderPublicOfficials();
  });
}

function renderPeopleList(people) {
  const directoryCount = $("directoryCount");
  if (directoryCount) {
    directoryCount.textContent = `${people.length} official${people.length === 1 ? "" : "s"}`;
  }
  $("peopleList").innerHTML =
    people
      .map(
        (person) => `
          <button class="person-button ${person.id === state.selectedId ? "active" : ""}" data-person-id="${person.id}">
            <strong>${escapeHtml(person.full_name)}</strong>
            <span>${escapeHtml(affiliation(person))}</span>
            <small>${fmt.format(person.roles.length)} role${person.roles.length === 1 ? "" : "s"}</small>
          </button>
        `
      )
      .join("") || '<p class="muted">No matching officials.</p>';

  document.querySelectorAll("[data-person-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedId = button.getAttribute("data-person-id");
      renderExplorer();
    });
  });
}

function timelineSvg(person) {
  const byMonth = new Map();
  for (const trade of person.trades) {
    const month = trade.trade_date.slice(0, 7);
    byMonth.set(month, (byMonth.get(month) || 0) + 1);
  }
  const months = [...byMonth.keys()].sort();
  const max = Math.max(...months.map((month) => byMonth.get(month)), 1);
  const width = 760;
  const height = 210;
  const padding = 34;
  const gap = 5;
  const barWidth = Math.max(8, (width - padding * 2 - gap * months.length) / Math.max(months.length, 1));
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly trade count">
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#d9e2dc"></line>
      ${months
        .map((month, index) => {
          const count = byMonth.get(month);
          const x = padding + index * (barWidth + gap);
          const barHeight = (height - padding * 2) * (count / max);
          const y = height - padding - barHeight;
          return `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="4" fill="#0f766e"><title>${month}: ${count} trades</title></rect>`;
        })
        .join("")}
      <text x="${padding}" y="24" fill="#64706a" font-size="14">${months[0] || ""}</text>
      <text x="${width - padding - 60}" y="24" fill="#64706a" font-size="14">${months.at(-1) || ""}</text>
    </svg>
  `;
}

function roleTimelineSvg(person) {
  const roles = [...person.roles].sort((a, b) => roleSortValue(a).localeCompare(roleSortValue(b)));
  const width = 760;
  const height = Math.max(150, 74 + roles.length * 34);
  const padding = 42;
  const dates = roles
    .flatMap((role) => [role.service_start, role.service_end].filter(Boolean))
    .sort();
  const minYear = dates[0] ? Number(dates[0].slice(0, 4)) : 2017;
  const maxYear = Math.max(
    dates.at(-1) ? Number(dates.at(-1).slice(0, 4)) : new Date().getFullYear(),
    new Date().getFullYear()
  );
  const yearSpan = Math.max(1, maxYear - minYear + 1);
  const xFor = (value) => {
    const year = value ? Number(value.slice(0, 4)) : maxYear;
    return padding + ((year - minYear) / yearSpan) * (width - padding * 2);
  };
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Official role timeline">
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#d9e2dc"></line>
      <text x="${padding}" y="${height - 14}" fill="#64706a" font-size="13">${minYear}</text>
      <text x="${width - padding - 34}" y="${height - 14}" fill="#64706a" font-size="13">${maxYear}</text>
      ${roles
        .map((role, index) => {
          const y = 36 + index * 34;
          const x1 = xFor(role.service_start);
          const x2 = Math.max(x1 + 18, xFor(role.service_end));
          const color = branchColors[role.branch] || "#0f766e";
          return `
            <line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${color}" stroke-width="8" stroke-linecap="round"></line>
            <circle cx="${x1}" cy="${y}" r="6" fill="${color}"></circle>
            <text x="${padding}" y="${y - 11}" fill="#17201d" font-size="13" font-weight="800">${escapeHtml(termLabel(role.presidential_term))}</text>
            <text x="${Math.min(width - 250, x1 + 12)}" y="${y + 5}" fill="#64706a" font-size="12">${escapeHtml(role.role_category.replaceAll("_", " "))}</text>
          `;
        })
        .join("")}
    </svg>
  `;
}

function marketSvg() {
  const rows = state.data.market.monthly;
  const width = 760;
  const height = 230;
  const padding = 34;
  const values = rows.flatMap((row) => [row.SPY, row.DIA]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const xFor = (index) => padding + (index / Math.max(rows.length - 1, 1)) * (width - padding * 2);
  const yFor = (value) =>
    height - padding - ((value - min) / Math.max(max - min, 1)) * (height - padding * 2);
  const line = (symbol) =>
    rows.map((row, index) => `${xFor(index)},${yFor(row[symbol])}`).join(" ");
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="SPY and DIA monthly trend">
      <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="#d9e2dc"></line>
      <polyline points="${line("SPY")}" fill="none" stroke="#0f766e" stroke-width="4"></polyline>
      <polyline points="${line("DIA")}" fill="none" stroke="#b7791f" stroke-width="4"></polyline>
      <text x="${padding}" y="24" fill="#0f766e" font-size="14" font-weight="800">SPY</text>
      <text x="${padding + 46}" y="24" fill="#b7791f" font-size="14" font-weight="800">DIA</text>
      <text x="${width - padding - 92}" y="24" fill="#64706a" font-size="14">${rows[0]?.month || ""} to ${rows.at(-1)?.month || ""}</text>
    </svg>
  `;
}

function renderProfile(person) {
  const recentTrades = [...(person.trades || [])]
    .sort((a, b) => b.trade_date.localeCompare(a.trade_date))
    .slice(0, 10);
  const latestRole = person.primary_role;
  const hasTrades = recentTrades.length > 0;
  $("profilePanel").innerHTML = `
    <div class="profile-header">
      <div>
        <p class="eyebrow">${escapeHtml(person.branch)}</p>
        <h2>${escapeHtml(person.full_name)}</h2>
        <p>${escapeHtml(affiliation(person))}</p>
      </div>
      <span class="badge gold">${hasTrades ? "Demo disclosure profile" : "Role roster profile"}</span>
    </div>

    <div class="profile-grid">
      <div class="mini-stat"><strong>${fmt.format(person.roles.length)}</strong><span>Tracked roles</span></div>
      <div class="mini-stat"><strong>${escapeHtml(latestRole ? termLabel(latestRole.presidential_term) : "n/a")}</strong><span>Latest term</span></div>
      <div class="mini-stat"><strong>${escapeHtml(latestRole?.role_category?.replaceAll("_", " ") || "n/a")}</strong><span>Role category</span></div>
      <div class="mini-stat"><strong>${hasTrades ? fmt.format(recentTrades.length) : "Pending"}</strong><span>Disclosure rows</span></div>
    </div>

    <div class="chart-shell">
      <div class="chart-title"><span>Role Timeline</span><span>${fmt.format(person.roles.length)} source-backed role${person.roles.length === 1 ? "" : "s"}</span></div>
      ${roleTimelineSvg(person)}
    </div>

    ${
      hasTrades
        ? `
          <div class="chart-shell">
            <div class="chart-title"><span>Monthly Transaction Timeline</span><span>Demo disclosure rows</span></div>
            ${timelineSvg(person)}
          </div>
          <div class="chart-shell">
            <div class="chart-title"><span>Market Context</span><span>SPY and DIA fixture overlay</span></div>
            ${marketSvg()}
          </div>
        `
        : ""
    }

    <div class="chart-shell">
      <div class="chart-title"><span>Official Role Records</span><span>Source-backed roster data</span></div>
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

    ${
      hasTrades
        ? `
          <div class="chart-shell">
            <div class="chart-title"><span>Recent Transaction Rows</span><span>Top 10 by trade date</span></div>
            <table class="trade-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Action</th>
                  <th>Asset</th>
                  <th>Range</th>
                  <th>Lag</th>
                </tr>
              </thead>
              <tbody>
                ${recentTrades
                  .map(
                    (trade) => `
                      <tr>
                        <td>${shortDate(trade.trade_date)}</td>
                        <td>${trade.action}</td>
                        <td>${escapeHtml(trade.asset_display_name)} ${trade.ticker ? `(${trade.ticker})` : ""}</td>
                        <td>${escapeHtml(trade.value_range_label)}</td>
                        <td>${trade.disclosure_lag_days}d</td>
                      </tr>
                    `
                  )
                  .join("")}
              </tbody>
            </table>
          </div>
        `
        : ""
    }
  `;
}

function renderExplorer() {
  const people = filteredPeople();
  if (!people.some((person) => person.id === state.selectedId)) {
    state.selectedId = people[0]?.id || state.explorerPeople[0]?.id || null;
  }
  renderPeopleList(people);
  const selected = state.explorerPeople.find((person) => person.id === state.selectedId);
  if (selected) renderProfile(selected);
}

function filteredOfficialRoles() {
  const query = state.officialQuery.trim().toLowerCase();
  return state.data.public_officials.roles.filter((role) => {
    const branchOk = !state.officialBranch || role.branch === state.officialBranch;
    const termOk = !state.officialTerm || role.presidential_term === state.officialTerm;
    const haystack = [
      role.full_name,
      role.branch,
      role.presidential_term,
      role.administration,
      role.role_category,
      role.role_title,
      role.office,
      role.agency,
      role.court,
      role.appointing_president,
      role.source_name,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return branchOk && termOk && (!query || haystack.includes(query));
  });
}

function renderPublicOfficials() {
  const summary = state.data.public_officials.summary;
  const byTerm = Object.entries(summary.role_counts_by_term)
    .map(
      ([term, count]) => `
        <div class="mini-stat">
          <strong>${fmt.format(count)}</strong>
          <span>${escapeHtml(termLabel(term))}</span>
        </div>
      `
    )
    .join("");
  $("officialsSummary").innerHTML = `
    <div class="profile-grid">
      <div class="mini-stat"><strong>${fmt.format(summary.person_count)}</strong><span>People</span></div>
      <div class="mini-stat"><strong>${fmt.format(summary.role_count)}</strong><span>Roles</span></div>
      <div class="mini-stat"><strong>${fmt.format(summary.role_counts_by_branch.Executive || 0)}</strong><span>Executive roles</span></div>
      <div class="mini-stat"><strong>${fmt.format(summary.role_counts_by_branch.Judicial || 0)}</strong><span>Judicial roles</span></div>
      ${byTerm}
    </div>
  `;

  const roles = filteredOfficialRoles();
  const limitedRoles = roles.slice(0, 120);
  $("officialRoleList").innerHTML = `
    <div class="chart-title">
      <span>${fmt.format(roles.length)} matching role${roles.length === 1 ? "" : "s"}</span>
      <span>Showing ${fmt.format(limitedRoles.length)} rows</span>
    </div>
    ${limitedRoles
      .map(
        (role) => `
          <article class="role-row">
            <div>
              <div class="role-title-line">
                <strong>${escapeHtml(role.full_name)}</strong>
                <span class="badge">${escapeHtml(role.branch)}</span>
                <span class="badge gold">${escapeHtml(termLabel(role.presidential_term))}</span>
              </div>
              <p>${escapeHtml(role.role_title)}</p>
              <small>${escapeHtml(role.court || role.agency || role.administration)}</small>
            </div>
            <div class="role-meta">
              <span>${shortDate(role.service_start)}</span>
              <span>${escapeHtml(role.role_category.replaceAll("_", " "))}</span>
              <a href="${escapeHtml(role.source_url)}" target="_blank" rel="noopener noreferrer">Source</a>
            </div>
          </article>
        `
      )
      .join("")}
  `;
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
  state.selectedId = state.explorerPeople[0]?.id || null;
  renderSummary();
  renderBranchChart();
  hydrateControls();
  renderPublicOfficials();
  renderExplorer();
  renderSources();
  renderEvents();
}

boot().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<main class="panel"><h1>CivicLedger</h1><p>Failed to load static demo data.</p></main>`;
});
