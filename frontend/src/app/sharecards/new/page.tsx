"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  DemoFixtureBanner,
  MetadataSummary,
  formatDateTime,
} from "@/components/ProvenanceStatus";
import { api } from "@/lib/api";
import type {
  MetaStatus,
  PersonDetail,
  TradeRow,
  ShareCardCreateResponse,
} from "@/lib/types";

function ShareCardBuilderInner() {
  const searchParams = useSearchParams();
  const personIdParam = searchParams.get("person_id") || "";
  const tradeIdParam = searchParams.get("trade_id") || "";

  const [personId, setPersonId] = useState(personIdParam);
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [scope, setScope] = useState<"trade" | "range">(tradeIdParam ? "trade" : "range");
  const [selectedTradeId, setSelectedTradeId] = useState(tradeIdParam);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [overlays, setOverlays] = useState(["SPY", "DIA"]);
  const [includeEvents, setIncludeEvents] = useState(true);
  const [result, setResult] = useState<ShareCardCreateResponse | null>(null);
  const [status, setStatus] = useState<MetaStatus | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

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
    if (personId) {
      api.getPerson(personId).then(setPerson).catch(() => setPerson(null));
      api
        .getPersonTrades(personId, { page_size: 50 })
        .then((d) => setTrades(d.items))
        .catch(() => setTrades([]));
    }
  }, [personId]);

  const handleGenerate = async () => {
    setError("");
    setGenerating(true);
    try {
      const data = await api.createShareCard({
        scope,
        person_id: personId,
        trade_id: scope === "trade" ? selectedTradeId : undefined,
        start: scope === "range" ? rangeStart : undefined,
        end: scope === "range" ? rangeEnd : undefined,
        overlays,
        include_events: includeEvents,
      });
      setResult(data);
    } catch (e: any) {
      setError(e.message || "Failed to generate share card.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Share Card Builder</h1>

      <DemoFixtureBanner status={status} className="mb-6" />

      <MetadataSummary
        className="mb-6"
        title="Dataset and Methodology Status"
        description="Metadata available before generating a share card."
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
        ]}
      />

      {person && (
        <p className="mb-4 text-gray-600">
          Creating card for <strong>{person.full_name}</strong> ({person.party},{" "}
          {person.state})
        </p>
      )}

      <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6 space-y-4">
        {/* Person ID */}
        {!personIdParam && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Person ID
            </label>
            <input
              type="text"
              value={personId}
              onChange={(e) => setPersonId(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              placeholder="UUID of the person"
            />
          </div>
        )}

        {/* Scope */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Scope
          </label>
          <div className="flex gap-3">
            <button
              onClick={() => setScope("trade")}
              className={`px-4 py-2 rounded border text-sm ${
                scope === "trade"
                  ? "bg-civic-600 text-white border-civic-600"
                  : "border-gray-300"
              }`}
            >
              Single Trade
            </button>
            <button
              onClick={() => setScope("range")}
              className={`px-4 py-2 rounded border text-sm ${
                scope === "range"
                  ? "bg-civic-600 text-white border-civic-600"
                  : "border-gray-300"
              }`}
            >
              Date Range
            </button>
          </div>
        </div>

        {/* Trade selector */}
        {scope === "trade" && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Select Trade
            </label>
            <select
              value={selectedTradeId}
              onChange={(e) => setSelectedTradeId(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            >
              <option value="">Choose a trade...</option>
              {trades.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.trade_date} — {t.action} {t.asset_display_name} (
                  {t.value_range_label})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Range inputs */}
        {scope === "range" && (
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Start
              </label>
              <input
                type="date"
                value={rangeStart}
                onChange={(e) => setRangeStart(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                End
              </label>
              <input
                type="date"
                value={rangeEnd}
                onChange={(e) => setRangeEnd(e.target.value)}
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>
        )}

        {/* Overlays */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Overlays
          </label>
          <div className="flex gap-3">
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={overlays.includes("SPY")}
                onChange={(e) =>
                  setOverlays(
                    e.target.checked
                      ? [...overlays, "SPY"]
                      : overlays.filter((o) => o !== "SPY")
                  )
                }
              />
              SPY
            </label>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={overlays.includes("DIA")}
                onChange={(e) =>
                  setOverlays(
                    e.target.checked
                      ? [...overlays, "DIA"]
                      : overlays.filter((o) => o !== "DIA")
                  )
                }
              />
              DIA
            </label>
          </div>
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={includeEvents}
            onChange={(e) => setIncludeEvents(e.target.checked)}
          />
          Include events on card
        </label>

        <button
          onClick={handleGenerate}
          disabled={
            generating ||
            !personId ||
            (scope === "trade" && !selectedTradeId) ||
            (scope === "range" && (!rangeStart || !rangeEnd))
          }
          className="px-6 py-2 bg-civic-600 text-white rounded hover:bg-civic-700 disabled:opacity-50 text-sm"
        >
          {generating ? "Generating..." : "Generate Share Card"}
        </button>

        {error && <p className="text-red-600 text-sm">{error}</p>}
      </div>

      {/* Result */}
      {result && (
        <>
          <MetadataSummary
            className="mb-4"
            title="Generated Card Metadata"
            description="Metadata returned with this generated share card."
            status={
              status ?? {
                dataset_version: result.dataset_version,
                methodology_version: result.methodology_version,
                parser_version: "Not returned",
                last_ingestion_run_at: null,
              }
            }
            items={[
              { label: "Dataset", value: result.dataset_version },
              { label: "Methodology", value: result.methodology_version },
              {
                label: "Generated",
                value: formatDateTime(result.generated_at),
                missingLabel: "Generation timestamp not provided",
              },
              {
                label: "Sources",
                value: result.sources.length
                  ? `${result.sources.length} provided`
                  : "",
                missingLabel: "No sources returned",
              },
            ]}
          />
          <div className="bg-white border border-gray-200 rounded-lg p-6">
            <h2 className="font-semibold mb-3">Share Card Generated</h2>
            <div className="text-sm space-y-2">
              <p>
                <span className="text-gray-400">Card ID:</span>{" "}
                <code className="text-xs bg-gray-100 px-1 py-0.5 rounded">
                  {result.sharecard_id}
                </code>
              </p>
              {result.sources.length > 0 && (
                <div>
                  <span className="text-gray-400">Sources:</span>
                  <ul className="ml-4 text-xs">
                    {result.sources.map((s, i) => (
                      <li key={i}>
                        <a
                          href={s}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-civic-600 hover:underline break-all"
                        >
                          {s}
                        </a>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
                {result.disclaimer_text}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function ShareCardBuilderPage() {
  return (
    <Suspense fallback={<p className="text-gray-400">Loading...</p>}>
      <ShareCardBuilderInner />
    </Suspense>
  );
}
