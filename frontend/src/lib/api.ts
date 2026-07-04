const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/api";

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

import type {
  PersonListResponse,
  PersonDetail,
  PersonSummary,
  ScorecardResponse,
  TimelineResponse,
  TradeListResponse,
  TradeDetail,
  FilingDetail,
  MarketSeriesItem,
  EventItem,
  ShareCardCreateResponse,
  MetaStatus,
  MethodologyResponse,
  OfficialSourcesResponse,
  SourceCompletenessResponse,
  ParserArtifactItem,
  BatchStatsItem,
} from "./types";

export const api = {
  // Meta
  getStatus: () => fetchAPI<MetaStatus>("/meta/status"),
  getMethodology: () => fetchAPI<MethodologyResponse>("/meta/methodology"),
  getSources: () => fetchAPI<OfficialSourcesResponse>("/meta/sources"),
  getSourceCompleteness: () =>
    fetchAPI<SourceCompletenessResponse>("/meta/source-completeness"),

  // Search
  searchPeople: (q: string) =>
    fetchAPI<PersonSummary[]>(`/search/people?q=${encodeURIComponent(q)}`),

  // People
  listPeople: (params: {
    branch?: string;
    chamber?: string;
    agency?: string;
    court?: string;
    state?: string;
    party?: string;
    sort?: string;
    page?: number;
    page_size?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params.branch) sp.set("branch", params.branch);
    if (params.chamber) sp.set("chamber", params.chamber);
    if (params.agency) sp.set("agency", params.agency);
    if (params.court) sp.set("court", params.court);
    if (params.state) sp.set("state", params.state);
    if (params.party) sp.set("party", params.party);
    if (params.sort) sp.set("sort", params.sort);
    if (params.page) sp.set("page", String(params.page));
    if (params.page_size) sp.set("page_size", String(params.page_size));
    return fetchAPI<PersonListResponse>(`/people?${sp.toString()}`);
  },

  getPerson: (id: string) => fetchAPI<PersonDetail>(`/people/${id}`),

  getScorecard: (id: string) =>
    fetchAPI<ScorecardResponse>(`/people/${id}/scorecard`),

  getTimeline: (
    id: string,
    params?: { start?: string; end?: string; bucket?: string }
  ) => {
    const sp = new URLSearchParams();
    if (params?.start) sp.set("start", params.start);
    if (params?.end) sp.set("end", params.end);
    if (params?.bucket) sp.set("bucket", params.bucket);
    return fetchAPI<TimelineResponse>(`/people/${id}/timeline?${sp.toString()}`);
  },

  getPersonTrades: (
    id: string,
    params?: {
      start?: string;
      end?: string;
      type?: string;
      asset_class?: string;
      min_lag?: number;
      sort?: string;
      page?: number;
      page_size?: number;
    }
  ) => {
    const sp = new URLSearchParams();
    if (params?.start) sp.set("start", params.start);
    if (params?.end) sp.set("end", params.end);
    if (params?.type) sp.set("type", params.type);
    if (params?.asset_class) sp.set("asset_class", params.asset_class);
    if (params?.min_lag) sp.set("min_lag", String(params.min_lag));
    if (params?.sort) sp.set("sort", params.sort);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.page_size) sp.set("page_size", String(params.page_size));
    return fetchAPI<TradeListResponse>(
      `/people/${id}/trades?${sp.toString()}`
    );
  },

  getBatchStats: (ids: string[], windowStart?: string, windowEnd?: string) => {
    const sp = new URLSearchParams();
    sp.set("ids", ids.join(","));
    if (windowStart) sp.set("window_start", windowStart);
    if (windowEnd) sp.set("window_end", windowEnd);
    return fetchAPI<{ by_id: Record<string, BatchStatsItem> }>(
      `/people/batch_stats?${sp.toString()}`
    );
  },

  // Trades
  getTrade: (id: string) => fetchAPI<TradeDetail>(`/trades/${id}`),
  getTradeArtifacts: (id: string) =>
    fetchAPI<ParserArtifactItem[]>(`/trades/${id}/artifacts`),

  // Filings
  getFiling: (id: string) => fetchAPI<FilingDetail>(`/filings/${id}`),
  getFilingArtifacts: (id: string) =>
    fetchAPI<ParserArtifactItem[]>(`/filings/${id}/artifacts`),

  // Market
  getMarketSeries: (params: {
    symbols?: string;
    start?: string;
    end?: string;
    freq?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params.symbols) sp.set("symbols", params.symbols);
    if (params.start) sp.set("start", params.start);
    if (params.end) sp.set("end", params.end);
    if (params.freq) sp.set("freq", params.freq);
    return fetchAPI<MarketSeriesItem[]>(`/market/series?${sp.toString()}`);
  },

  // Events
  getEvents: (params?: {
    scope?: string;
    person_id?: string;
    start?: string;
    end?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.scope) sp.set("scope", params.scope);
    if (params?.person_id) sp.set("person_id", params.person_id);
    if (params?.start) sp.set("start", params.start);
    if (params?.end) sp.set("end", params.end);
    return fetchAPI<EventItem[]>(`/events?${sp.toString()}`);
  },

  getEvent: (id: string) => fetchAPI<EventItem>(`/events/${id}`),

  // Share Cards
  createShareCard: (data: {
    scope: string;
    person_id: string;
    trade_id?: string;
    start?: string;
    end?: string;
    overlays?: string[];
    include_events?: boolean;
  }) =>
    fetchAPI<ShareCardCreateResponse>("/sharecards", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
