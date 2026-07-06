"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ParserArtifactItem } from "@/lib/types";

export default function EvidencePage() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ParserArtifactItem[]>([]);
  const [message, setMessage] = useState("");

  async function search() {
    if (query.trim().length < 2) return;
    setMessage("");
    try {
      const response = await api.searchEvidence({ q: query.trim() });
      setItems(response.items);
      setMessage(`${response.total} result${response.total === 1 ? "" : "s"}`);
    } catch (error) {
      setItems([]);
      setMessage(error instanceof Error ? error.message : "Search failed.");
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold">Evidence Search</h1>
      <div className="mt-5 flex max-w-2xl gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") search();
          }}
          className="min-w-0 flex-1 rounded-md border px-3 py-2 text-sm"
          placeholder="Search parser output, text spans, or source IDs"
        />
        <button
          onClick={search}
          className="rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white"
        >
          Search
        </button>
      </div>
      {message ? <p className="mt-3 text-sm text-gray-500">{message}</p> : null}

      <div className="mt-6 space-y-3">
        {items.map((artifact) => (
          <article key={artifact.id} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex flex-wrap gap-3 text-xs text-gray-500">
              <span>{artifact.source_id}</span>
              <span>{artifact.artifact_type}</span>
              <Link href={`/raw-documents/${artifact.raw_document_id}`} className="text-civic-700 underline">
                Raw document
              </Link>
              {artifact.filing_id ? (
                <Link href={`/filings/${artifact.filing_id}/evidence`} className="text-civic-700 underline">
                  Filing
                </Link>
              ) : null}
              {artifact.trade_id ? (
                <Link href={`/trades/${artifact.trade_id}`} className="text-civic-700 underline">
                  Trade
                </Link>
              ) : null}
            </div>
            <pre className="mt-3 max-h-56 overflow-auto rounded bg-gray-50 p-3 text-xs">
              {JSON.stringify(artifact.parser_output, null, 2)}
            </pre>
          </article>
        ))}
      </div>
    </div>
  );
}
