"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  DemoFixtureBanner,
  MetadataSummary,
  StatusBadge,
  formatDateTime,
} from "@/components/ProvenanceStatus";
import { api } from "@/lib/api";
import type {
  TradeDetail,
  MarketSeriesItem,
  MetaStatus,
  ParserArtifactItem,
} from "@/lib/types";
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
  const [artifacts, setArtifacts] = useState<ParserArtifactItem[]>([]);
  const [status, setStatus] = useState<MetaStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .getStatus()
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) setStatus(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

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

        return Promise.all([
          api.getMarketSeries({
            symbols: "SPY,DIA",
            start: start.toISOString().split("T")[0],
            end: end.toISOString().split("T")[0],
          }),
          api.getTradeArtifacts(tradeId).catch(() => []),
        ]);
      })
      .then(([series, evidence]) => {
        setMarketData(series);
        setArtifacts(evidence);
      })
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
  const provenance = trade.provenance;
  const provenanceComplete = provenance?.provenance_complete === true;
  const provenanceMissing = provenance?.provenance_complete === false || !provenance;
  const provenanceLabel = provenanceComplete
    ? "Complete"
    : provenanceMissing
    ? "Incomplete"
    : "Not provided";

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

      <DemoFixtureBanner status={status} className="mb-6" />

      <MetadataSummary
        className="mb-6"
        title="Dataset and Trade Provenance"
        description="Available dataset, methodology, and source metadata for this trade."
        status={status}
        items={[
          { label: "Dataset", value: status?.dataset_version },
          { label: "Methodology", value: status?.methodology_version },
          { label: "Parser", value: status?.parser_version },
          {
            label: "Last ingestion",
            value: formatDateTime(status?.last_ingestion_run_at),
            missingLabel: "No completed ingestion timestamp",
          },
          {
            label: "Provenance",
            value: provenanceLabel,
            missingLabel: "Completeness not provided",
          },
          {
            label: "Retrieved",
            value: formatDateTime(provenance?.retrieved_at),
            missingLabel: "Retrieval timestamp not provided",
          },
          {
            label: "File hash",
            value: provenance?.file_hash,
            missingLabel: "File hash not provided",
          },
          {
            label: "Market overlay",
            value: chartPoints.length > 0 ? "SPY loaded" : "",
            missingLabel: "No SPY overlay loaded",
          },
          {
            label: "Parser artifacts",
            value: artifacts.length > 0 ? `${artifacts.length} linked` : "",
            missingLabel: "No parser artifacts linked",
          },
        ]}
      />

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
          <span className="ml-2">
            <StatusBadge
              tone={
                provenanceComplete
                  ? "complete"
                  : provenanceMissing
                  ? "attention"
                  : "neutral"
              }
            >
              {provenanceLabel}
            </StatusBadge>
          </span>
        </h2>
        <div className="text-sm space-y-1">
          <p>
            <span className="text-gray-400 w-24 inline-block">Source:</span>
            {provenance?.source_url ? (
              <a
                href={provenance.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-civic-600 hover:underline break-all"
              >
                {provenance.source_url}
              </a>
            ) : (
              <span className="text-gray-400">Not provided</span>
            )}
          </p>
          <p>
            <span className="text-gray-400 w-24 inline-block">Retrieved:</span>
            {formatDateTime(provenance?.retrieved_at) || (
              <span className="text-gray-400">Not provided</span>
            )}
          </p>
          <p>
            <span className="text-gray-400 w-24 inline-block">File Hash:</span>
            {provenance?.file_hash ? (
              <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">
                {provenance.file_hash}
              </code>
            ) : (
              <span className="text-gray-400">Not provided</span>
            )}
          </p>
        </div>
      </div>

      {/* Parser evidence panel */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 mb-6">
        <h2 className="font-semibold text-sm text-gray-700 mb-3">
          Parser Evidence
        </h2>
        {artifacts.length === 0 ? (
          <div className="text-sm text-gray-500">No parser artifacts linked.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="border-b text-gray-500">
                <tr>
                  <th className="py-2 pr-4 font-medium">Source</th>
                  <th className="py-2 pr-4 font-medium">Type</th>
                  <th className="py-2 pr-4 font-medium">Location</th>
                  <th className="py-2 pr-4 font-medium">Confidence</th>
                  <th className="py-2 pr-4 font-medium">Evidence</th>
                  <th className="py-2 pr-4 font-medium">Evidence Text</th>
                </tr>
              </thead>
              <tbody>
                {artifacts.map((artifact) => (
                  <tr key={artifact.id} className="border-b last:border-0">
                    <td className="py-2 pr-4 font-mono text-gray-700">
                      {artifact.source_id}
                    </td>
                    <td className="py-2 pr-4">{artifact.artifact_type}</td>
                    <td className="py-2 pr-4 text-gray-600">
                      {[
                        artifact.page_number ? `p.${artifact.page_number}` : "",
                        artifact.row_number ? `row ${artifact.row_number}` : "",
                      ]
                        .filter(Boolean)
                        .join(", ") || "Not provided"}
                    </td>
                    <td className="py-2 pr-4">
                      {artifact.confidence != null
                        ? `${(Number(artifact.confidence) * 100).toFixed(0)}%`
                        : "Not provided"}
                    </td>
                    <td className="py-2 pr-4">
                      <div className="flex flex-col gap-1">
                        <Link
                          href={`/raw-documents/${artifact.raw_document_id}`}
                          className="text-civic-700 underline"
                        >
                          Raw document
                        </Link>
                        {artifact.filing_id ? (
                          <Link
                            href={`/filings/${artifact.filing_id}/evidence`}
                            className="text-civic-700 underline"
                          >
                            Filing evidence
                          </Link>
                        ) : null}
                      </div>
                    </td>
                    <td className="max-w-md py-2 pr-4 text-gray-600">
                      {typeof artifact.text_span?.text === "string"
                        ? artifact.text_span.text
                        : "No text span provided"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
