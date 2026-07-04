"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  EventItem,
  MarketSeriesItem,
  PersonDetail,
  ScorecardResponse,
  TimelineResponse,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/api";

function fmtDate(d?: string) {
  if (!d) return "—";
  return d;
}

function safeEventId(e: EventItem) {
  return e.event_id;
}

function safeEventTitle(e: EventItem) {
  return e.label;
}

function safeEventType(e: EventItem) {
  return e.event_type;
}

function monthKeyFromDate(dateStr: string) {
  // "2023-01-23" -> "2023-01"
  return dateStr.slice(0, 7);
}

function normalizeMarketToMonths(series: MarketSeriesItem[], months: string[]) {
  // For each symbol, create a month->lastValue mapping and align to timeline months
  const out: Record<string, Record<string, number | null>> = {};
  for (const s of series) {
    const map: Record<string, number> = {};
    for (const p of s.points ?? []) {
      const m = monthKeyFromDate(p.date);
      map[m] = p.value; // last write wins -> last point in that month
    }
    // Fill aligned (null for missing)
    out[s.symbol] = {};
    for (const m of months) {
      out[s.symbol][m] = map[m] ?? null;
    }
  }
  return out;
}

export default function ProfilePage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;

  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [marketData, setMarketData] = useState<MarketSeriesItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);

  const [showSPY, setShowSPY] = useState(true);
  const [showDIA, setShowDIA] = useState(false);
  const [showEvents, setShowEvents] = useState(true);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Load core profile + scorecard + timeline
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setErr(null);

      try {
        const [pRes, sRes, tRes] = await Promise.all([
          fetch(`${API_BASE}/people/${id}`, { cache: "no-store" }),
          fetch(`${API_BASE}/people/${id}/scorecard`, { cache: "no-store" }),
          fetch(`${API_BASE}/people/${id}/timeline?bucket=month`, { cache: "no-store" }),
        ]);

        if (!pRes.ok) throw new Error(`Person fetch failed (${pRes.status})`);
        if (!sRes.ok) throw new Error(`Scorecard fetch failed (${sRes.status})`);
        if (!tRes.ok) throw new Error(`Timeline fetch failed (${tRes.status})`);

        const pJson = await pRes.json();
        const sJson = await sRes.json();
        const tJson = await tRes.json();

        if (cancelled) return;
        setPerson(pJson);
        setScorecard(sJson);
        setTimeline(tJson);
      } catch (e: any) {
        if (!cancelled) setErr(e?.message ?? "Failed to load profile.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Load market overlays + events once we have timeline bounds
  useEffect(() => {
    let cancelled = false;

    async function loadSecondary() {
      if (!timeline) return;

      const start = timeline.start;
      const end = timeline.end;
      if (!start || !end) {
        setMarketData([]);
        setEvents([]);
        return;
      }

      // market overlays (SPY default; DIA optional)
      const symbols = ["SPY", "DIA"].join(",");
      try {
        const mRes = await fetch(
          `${API_BASE}/market/series?symbols=${encodeURIComponent(symbols)}&start=${encodeURIComponent(
            start
          )}&end=${encodeURIComponent(end)}&freq=d`,
          { cache: "no-store" }
        );
        if (mRes.ok) {
          const mJson = await mRes.json();
          if (!cancelled) setMarketData(Array.isArray(mJson) ? mJson : mJson.series ?? []);
        } else {
          // don't hard-fail the page for overlays
          if (!cancelled) setMarketData([]);
        }
      } catch {
        if (!cancelled) setMarketData([]);
      }

      try {
        const eUrl =
          `${API_BASE}/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;

        const eRes = await fetch(eUrl, { cache: "no-store" });
        if (eRes.ok) {
          const eJson = await eRes.json();
          const list = Array.isArray(eJson) ? eJson : eJson.items ?? eJson.events ?? [];
          if (!cancelled) setEvents(list);
        } else {
          if (!cancelled) setEvents([]);
        }
      } catch {
        if (!cancelled) setEvents([]);
      }
    }

    loadSecondary();
    return () => {
      cancelled = true;
    };
  }, [timeline, id]);

  const chartData = useMemo(() => {
    if (!timeline) return [];

    const months = timeline.buckets.map((b) => b.start.slice(0, 7));
    const marketByMonth = normalizeMarketToMonths(marketData, months);

    // build recharts-friendly rows
    return timeline.buckets.map((b) => {
      const m = b.start.slice(0, 7);
      return {
        month: m,
        buys: b.buy_count ?? 0,
        sells: b.sell_count ?? 0,
        trades: b.trade_count ?? 0,
        SPY: marketByMonth["SPY"]?.[m] ?? null,
        DIA: marketByMonth["DIA"]?.[m] ?? null,
      };
    });
  }, [timeline, marketData]);

  const eventsInRangeNumbered = useMemo(() => {
    if (!timeline) return [];
    // Keep list stable, sorted by date
    const list = [...events].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    return list.map((e, idx) => ({
      ...e,
      _n: idx + 1,
    }));
  }, [events, timeline]);

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <div className="text-sm text-gray-600">Loading…</div>
      </main>
    );
  }

  if (err || !person) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {err ?? "Person not found."}
          <div className="mt-3">
            <Link href="/browse" className="underline hover:text-blue-600">
              Back to Browse
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const score = scorecard?.completeness_rating ?? 0;
  const grade = scorecard?.grade ?? (score >= 90 ? "A" : score >= 80 ? "B" : score >= 70 ? "C" : score >= 60 ? "D" : "F");
  const scorecardNotes = scorecard?.notes?.join("; ") ?? "—";

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="mb-2">
            <Link href="/" className="text-sm underline hover:text-blue-600">
              Home
            </Link>
            <span className="mx-2 text-gray-400">/</span>
            <Link href="/browse" className="text-sm underline hover:text-blue-600">
              Browse
            </Link>
          </div>

          <h1 className="text-2xl font-semibold">{person.full_name}</h1>
          <div className="mt-1 text-sm text-gray-600">
            {(person.party ?? "—") + " · " + (person.chamber ?? "—") + " · " + (person.state ?? "—")}
            {person.district ? ` (${person.state}-${person.district})` : ""}
          </div>
          <div className="mt-1 text-xs text-gray-500">
            Serving since {fmtDate(person.service_start)}
            {person.service_end ? ` · Ended ${fmtDate(person.service_end)}` : ""}
          </div>
        </div>

        {/* Score badge */}
        <div className="w-full max-w-[180px] rounded-lg border bg-white p-4 text-center shadow-sm">
          <div className="text-3xl font-bold">{grade}</div>
          <div className="mt-1 text-sm text-gray-700">{score}/100</div>
          <div className="mt-1 text-xs text-gray-500">Disclosure Completeness</div>
        </div>
      </div>

      {/* Scorecard summary */}
      <div className="mt-6 rounded-lg border bg-white p-4">
        <div className="text-sm font-semibold">Scorecard Summary</div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
          <div>
            <div className="text-xs text-gray-500">Reporting</div>
            <div className="text-sm">{scorecard?.transaction_level_reporting ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Median Lag</div>
            <div className="text-sm">
              {scorecard?.typical_reporting_lag_days != null
                ? `${scorecard.typical_reporting_lag_days} days`
                : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Type</div>
            <div className="text-sm">{scorecard?.disclosure_type ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Notes</div>
            <div className="text-sm">{scorecardNotes}</div>
          </div>
        </div>
      </div>

      {/* Toggles */}
      <div className="mt-4 flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showSPY}
            onChange={(e) => setShowSPY(e.target.checked)}
          />
          SPY overlay
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showDIA}
            onChange={(e) => setShowDIA(e.target.checked)}
          />
          DIA overlay
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showEvents}
            onChange={(e) => setShowEvents(e.target.checked)}
          />
          Show global events
        </label>

        <div className="ml-auto flex items-center gap-3">
          <Link
            href={`/people/${person.person_id}/trades`}
            className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50"
          >
            View Trades
          </Link>
          <Link
            href={`/sharecards/new?person_id=${person.person_id}`}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
          >
            Create Share Card
          </Link>
        </div>
      </div>

      {/* Chart */}
      <div className="mt-4 rounded-lg border bg-white p-4">
        <div className="mb-3 text-sm font-semibold">Trade Density Timeline (Monthly)</div>

        {chartData.length === 0 ? (
          <div className="text-sm text-gray-600">No timeline data.</div>
        ) : (
          <div className="h-[360px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" />
                <Tooltip />
                <Legend />

                <Bar yAxisId="left" dataKey="buys" name="Buys" />
                <Bar yAxisId="left" dataKey="sells" name="Sells" />

                {showSPY ? (
                  <Line yAxisId="right" type="monotone" dataKey="SPY" name="SPY" dot={false} />
                ) : null}
                {showDIA ? (
                  <Line yAxisId="right" type="monotone" dataKey="DIA" name="DIA" dot={false} />
                ) : null}

                {/* Event on-chart markers (low clutter) can be added next with ReferenceLine/ReferenceDot */}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Events List */}
      {showEvents ? (
        <div className="mt-4 rounded-lg border bg-white p-4">
          <div className="mb-2 text-sm font-semibold">Global Context Events</div>
          {eventsInRangeNumbered.length === 0 ? (
            <div className="text-sm text-gray-600">No events in this range.</div>
          ) : (
            <div className="space-y-2">
              {eventsInRangeNumbered.map((e) => {
                const eid = safeEventId(e);
                return (
                  <div key={`${e.date}-${eid || safeEventTitle(e)}`} className="flex items-start gap-3">
                    <div className="mt-0.5 w-6 shrink-0 text-right text-xs font-mono text-gray-500">
                      {e._n}.
                    </div>
                    <div className="flex-1">
                      <div className="text-xs text-gray-500">{e.date}</div>
                      <div className="text-sm">
                        <span className="font-medium">{safeEventTitle(e)}</span>
                        {safeEventType(e) ? (
                          <span className="ml-2 rounded bg-gray-100 px-2 py-0.5 text-xs">
                            {safeEventType(e)}
                          </span>
                        ) : null}
                      </div>
                      {e.description ? (
                        <div className="mt-0.5 text-xs text-gray-600">{e.description}</div>
                      ) : null}
                    </div>

                    {/* Sources link (no clutter) */}
                    <div className="shrink-0">
                      {eid ? (
                        <Link
                          href={`/events/${eid}/sources`}
                          className="text-xs underline hover:text-blue-600"
                        >
                          Sources
                        </Link>
                      ) : (
                        <span className="text-xs text-gray-400">Sources</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : null}
    </main>
  );
}
