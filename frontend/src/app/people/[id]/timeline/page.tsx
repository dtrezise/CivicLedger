"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type {
  PersonDetail,
  TimelineResponse,
  MarketSeriesItem,
  EventItem,
} from "@/lib/types";
import {
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ComposedChart,
  Legend,
} from "recharts";

const BUCKETS = ["month", "week", "day"] as const;
type Bucket = (typeof BUCKETS)[number];

function bucketLabel(bucket: Bucket, start: string) {
  if (bucket === "day") return start;
  if (bucket === "week") return `W ${start.slice(5)}`;
  return start.slice(0, 7);
}

function eventBucketLabel(evt: EventItem, timeline: TimelineResponse, bucket: Bucket) {
  if (bucket === "month") return evt.date.slice(0, 7);
  if (bucket === "day") return evt.date;

  const matchingBucket = timeline.buckets.find(
    (b) => b.start <= evt.date && evt.date <= b.end
  );
  return matchingBucket ? bucketLabel(bucket, matchingBucket.start) : evt.date;
}

export default function TimelinePage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [marketData, setMarketData] = useState<MarketSeriesItem[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [bucket, setBucket] = useState<Bucket>("month");
  const [showSPY, setShowSPY] = useState(true);
  const [showDIA, setShowDIA] = useState(false);
  const [showEvents, setShowEvents] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError("");
    api
      .getPerson(id)
      .then(async (p) => {
        const t = await api.getTimeline(id, { bucket });
        if (cancelled) return;
        setPerson(p);
        setTimeline(t);
      })
      .catch((err) => {
        if (!cancelled) {
          setPerson(null);
          setTimeline(null);
          setError(err instanceof Error ? err.message : "Failed to load timeline.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [id, bucket]);

  useEffect(() => {
    let cancelled = false;

    async function loadOverlays() {
      if (!timeline?.start || !timeline.end) {
        setMarketData([]);
        setEvents([]);
        return;
      }

      const [market, globalEvents] = await Promise.allSettled([
        api.getMarketSeries({
          symbols: "SPY,DIA",
          start: timeline.start,
          end: timeline.end,
        }),
        api.getEvents({ start: timeline.start, end: timeline.end }),
      ]);

      if (cancelled) return;
      setMarketData(market.status === "fulfilled" ? market.value : []);
      setEvents(globalEvents.status === "fulfilled" ? globalEvents.value : []);
    }

    loadOverlays();
    return () => {
      cancelled = true;
    };
  }, [timeline]);

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!person) return <p className="text-red-500">{error || "Not found."}</p>;

  const chartData = (timeline?.buckets || []).map((b) => {
    const label = bucketLabel(bucket, b.start);

    const entry: Record<string, any> = {
      label,
      trade_count: b.trade_count,
      buy_count: b.buy_count,
      sell_count: b.sell_count,
      median_lag: b.median_lag_days,
    };

    for (const series of marketData) {
      const pt = [...series.points].reverse().find((p) => p.date <= b.end);
      if (pt) entry[series.symbol] = Number(pt.value);
    }
    return entry;
  });

  return (
    <div>
      <div className="mb-4">
        <Link href={`/people/${id}`} className="text-sm text-civic-600 hover:underline">
          &larr; Back to profile
        </Link>
      </div>

      <h1 className="text-2xl font-bold mb-1">{person.full_name}</h1>
      <h2 className="text-gray-500 mb-6">Timeline Detail</h2>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-gray-500">Bucket:</span>
          {BUCKETS.map((b) => (
            <button
              key={b}
              onClick={() => setBucket(b)}
              className={`px-3 py-1 rounded border text-xs ${
                bucket === b
                  ? "bg-civic-600 text-white border-civic-600"
                  : "border-gray-300"
              }`}
            >
              {b}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={showSPY} onChange={(e) => setShowSPY(e.target.checked)} />
          SPY
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={showDIA} onChange={(e) => setShowDIA(e.target.checked)} />
          DIA
        </label>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} />
          Global events
        </label>
      </div>

      {/* Chart */}
      {chartData.length > 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
          <ResponsiveContainer width="100%" height={450}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} />
              <YAxis yAxisId="trades" orientation="left" />
              <YAxis yAxisId="market" orientation="right" />
              <Tooltip />
              <Legend />
              <Bar yAxisId="trades" dataKey="buy_count" stackId="t" fill="#4ade80" name="Buys" />
              <Bar yAxisId="trades" dataKey="sell_count" stackId="t" fill="#f87171" name="Sells" />
              {showSPY && (
                <Line yAxisId="market" type="monotone" dataKey="SPY" stroke="#6366f1" dot={false} name="SPY" />
              )}
              {showDIA && (
                <Line yAxisId="market" type="monotone" dataKey="DIA" stroke="#f59e0b" dot={false} name="DIA" />
              )}
              {showEvents &&
                events.map((evt) => (
                  <ReferenceLine
                    key={evt.event_id}
                    yAxisId="trades"
                    x={timeline ? eventBucketLabel(evt, timeline, bucket) : evt.date}
                    stroke="#94a3b8"
                    strokeDasharray="3 3"
                  />
                ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="text-gray-400">No data for this range.</p>
      )}

      {/* Events rail */}
      {showEvents && events.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-sm mb-2">Global Context Events</h3>
          <div className="space-y-1">
            {events.map((e) => (
              <div key={e.event_id} className="flex gap-3 text-xs">
                <span className="text-gray-400 w-20 shrink-0">{e.date}</span>
                <span>{e.label}</span>
                <span className="px-1 bg-gray-100 rounded">{e.event_type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Gaps */}
      {timeline?.gaps && timeline.gaps.length > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-6">
          <h3 className="font-semibold text-sm text-yellow-800 mb-2">Gaps Detected</h3>
          <ul className="text-xs text-yellow-700 space-y-1">
            {timeline.gaps.map((g, i) => (
              <li key={i}>{g.display_label}</li>
            ))}
          </ul>
        </div>
      )}

      <Link
        href={`/people/${id}/trades`}
        className="inline-block px-4 py-2 bg-civic-600 text-white rounded text-sm hover:bg-civic-700"
      >
        View Trades List
      </Link>
    </div>
  );
}
