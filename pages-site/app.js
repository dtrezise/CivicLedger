const state = {
  data: null,
  selectedId: null,
  query: "",
  branch: "",
  assetClass: "",
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

function filteredPeople() {
  const query = state.query.trim().toLowerCase();
  return state.data.people.filter((person) => {
    const branchOk = !state.branch || person.branch === state.branch;
    const assetOk =
      !state.assetClass ||
      person.trades.some((trade) => trade.asset_class === state.assetClass);
    const haystack = [
      person.full_name,
      person.branch,
      person.chamber,
      person.office,
      person.agency,
      person.court,
      person.state,
      person.party,
      ...person.trades.map((trade) => `${trade.asset_display_name} ${trade.ticker}`),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return branchOk && assetOk && (!query || haystack.includes(query));
  });
}

function renderSummary() {
  const summary = state.data.summary;
  $("demoNotice").innerHTML = `
    <strong>Public demo notice</strong>
    <span>${escapeHtml(state.data.disclaimer)}</span>
  `;
  $("summaryMetrics").innerHTML = [
    ["Officials", summary.official_count],
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
  const entries = Object.entries(state.data.summary.branch_counts);
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
      <text x="24" y="296" fill="#64706a" font-size="15">Generated fixture data used for public UI evaluation.</text>
    </svg>
  `;
}

function hydrateControls() {
  const branches = [...new Set(state.data.people.map((person) => person.branch))].sort();
  $("branchFilter").innerHTML =
    '<option value="">All branches</option>' +
    branches.map((branch) => `<option value="${branch}">${branch}</option>`).join("");

  const assets = [
    ...new Set(state.data.trades.map((trade) => trade.asset_class).filter(Boolean)),
  ].sort();
  $("assetFilter").innerHTML =
    '<option value="">All assets</option>' +
    assets
      .map((asset) => `<option value="${asset}">${asset.replaceAll("_", " ")}</option>`)
      .join("");

  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderExplorer();
  });
  $("branchFilter").addEventListener("change", (event) => {
    state.branch = event.target.value;
    renderExplorer();
  });
  $("assetFilter").addEventListener("change", (event) => {
    state.assetClass = event.target.value;
    renderExplorer();
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
  const recentTrades = [...person.trades]
    .sort((a, b) => b.trade_date.localeCompare(a.trade_date))
    .slice(0, 10);
  const score = person.scorecard;
  $("profilePanel").innerHTML = `
    <div class="profile-header">
      <div>
        <p class="eyebrow">${escapeHtml(person.branch)}</p>
        <h2>${escapeHtml(person.full_name)}</h2>
        <p>${escapeHtml(affiliation(person))}</p>
      </div>
      <span class="badge gold">Grade ${score.grade} / ${score.score}</span>
    </div>

    <div class="profile-grid">
      <div class="mini-stat"><strong>${fmt.format(person.stats.trade_count)}</strong><span>Trades</span></div>
      <div class="mini-stat"><strong>${fmt.format(person.stats.filing_count)}</strong><span>Filings</span></div>
      <div class="mini-stat"><strong>${score.median_lag_days ?? "n/a"}</strong><span>Median lag days</span></div>
      <div class="mini-stat"><strong>${money.format(person.stats.total_reported_min)}</strong><span>Minimum reported range</span></div>
    </div>

    <div class="chart-shell">
      <div class="chart-title"><span>Monthly Transaction Timeline</span><span>${person.stats.buy_count} buys / ${person.stats.sell_count} sells</span></div>
      ${timelineSvg(person)}
    </div>

    <div class="chart-shell">
      <div class="chart-title"><span>Market Context</span><span>SPY and DIA fixture overlay</span></div>
      ${marketSvg()}
    </div>

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
  `;
}

function renderExplorer() {
  const people = filteredPeople();
  if (!people.some((person) => person.id === state.selectedId)) {
    state.selectedId = people[0]?.id || state.data.people[0]?.id || null;
  }
  renderPeopleList(people);
  const selected = state.data.people.find((person) => person.id === state.selectedId);
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
  state.selectedId = state.data.people[0]?.id || null;
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
