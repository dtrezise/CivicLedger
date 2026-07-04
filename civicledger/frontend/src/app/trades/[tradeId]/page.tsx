"use client";

import { useState, useEffect, use } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { TradeDetail, MarketSeriesItem } from "@/lib/types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

export default function TradeDetailPage({
  params,
}: {
  params: { tradeId: string };
}) {
  const { tradeId } = params;
  const [trade, setTrade] = useState<TradeDetail | null>(null);
  const [marketData, setMarketData] = useState<MarketSeriesItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getTrade(tradeId)
      .then((t) => {
        setTrade(t);
        // Fetch market data around trade date (+/- 60 days)
        const td = new Date(t.trade_date);
        const start = new Date(td);
        start.setDate(start.getDate() - 30);
        const end = new Date(td);
        end.setDate(end.getDate() + 60);

        return api.getMarketSeries({
          symbols: "SPY,DIA",
          start: start.toISOString().split("T")[0],
          end: end.toISOString().split("T")[0],
        });
      })
      .then(setMarketData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [tradeId]);

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!trade) return <p className="text-red-500">Trade not found.</p>;

  // Mini benchmark chart data
  const spyData = marketData.find((m) => m.symbol === "SPY");
  const chartPoints = (spyData?.points || []).map((p) => ({
    date: p.date,
    value: Number(p.value),
  }));

  return (
    <div>
      <div className="mb-4">
        <Link
          href={`/people/${trade.person_id}/trades`}
          className="text-sm text-civic-600 hover:underline"
        >
          &larr; Back to trades
        </Link>
      </div>

      <h1 className="text-2xl font-bold mb-1">Trade Detail</h1>
      <p className="text-gray-500 mb-6">{trade.asset_display_name}</p>

      {/* Facts grid */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-xs text-gray-400">Action</div>
            <div
              className={`font-medium ${
                trade.action === "BUY" ? "text-green-700" : trade.action === "SELL" ? "text-red-700" : ""
              }`}
            >
              {trade.action}
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Trade Date</div>
            <div>{trade.trade_date}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Reported Date</div>
            <div>{trade.reported_date}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Ticker</div>
            <div className="font-mono">{trade.ticker || "N/A"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Asset Class</div>
            <div>{trade.asset_class}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Value Range</div>
            <div>{trade.value_range_label}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Disclosure Lag</div>
            <div
              className={
                trade.disclosure_lag_days > 60
                  ? "text-red-600"
                  : trade.disclosure_lag_days > 30
                  ? "text-yellow-600"
                  : "text-green-600"
              }
            >
              {trade.disclosure_lag_days} days
            </div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Raw Asset Text</div>
            <div className="text-xs">{trade.raw_asset_text}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">Parsing Confidence</div>
            <div>
              {trade.parsing_confidence
                ? `${(Number(trade.parsing_confidence) * 100).toFixed(0)}%`
                : "N/A"}
            </div>
          </div>
        </div>
      </div>

      {/* Provenance panel */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
        <h2 className="font-semibold text-sm text-gray-700 mb-2">
          Provenance
          {!trade.provenance.provenance_complete && (
            <span className="ml-2 text-xs text-yellow-600 bg-yellow-50 px-2 py-0.5 rounded">
              Incomplete
            </span>
          )}
        </h2>
        <div className="text-sm space-y-1">
          <p>
            <span className="text-gray-400 w-24 inline-block">Source:</span>
            <a
              href={trade.provenance.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-civic-600 hover:underline break-all"
            >
              {trade.provenance.source_url}
            </a>
          </p>
          <p>
            <span className="text-gray-400 w-24 inline-block">Retrieved:</span>
            {trade.provenance.retrieved_at
              ? new Date(trade.provenance.retrieved_at).toLocaleString()
              : "N/A"}
          </p>
          <p>
            <span className="text-gray-400 w-24 inline-block">File Hash:</span>
            <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">
              {trade.provenance.file_hash}
            </code>
          </p>
        </div>
      </div>

      {/* Mini benchmark chart */}
      {chartPoints.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
          <h2 className="font-semibold text-sm text-gray-700 mb-3">
            SPY Around Trade Date
          </h2>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={chartPoints}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#6366f1"
                dot={false}
              />
              <ReferenceLine
                x={trade.trade_date}
                stroke="#ef4444"
                strokeDasharray="5 5"
                label={{
                  value: "Trade",
                  position: "top",
                  style: { fontSize: 10, fill: "#ef4444" },
                }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
