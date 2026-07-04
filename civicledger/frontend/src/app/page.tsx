"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { PersonSummary, MetaStatus } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PersonSummary[]>([]);
  const [status, setStatus] = useState<MetaStatus | null>(null);
  const [showResults, setShowResults] = useState(false);

  useEffect(() => {
    api.getStatus().then(setStatus).catch(console.error);
  }, []);

  const search = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      return;
    }
    try {
      const data = await api.searchPeople(q);
      setResults(data);
    } catch {
      setResults([]);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => search(query), 300);
    return () => clearTimeout(timer);
  }, [query, search]);

  return (
    <div className="flex flex-col items-center pt-16">
      <h1 className="text-4xl font-bold text-civic-800 mb-2">CivicLedger</h1>
      <p className="text-gray-500 mb-8 text-center max-w-lg">
        Track financial disclosures by members of the U.S. Congress. Search for
        a member to view their trading timeline, scorecard, and provenance data.
      </p>

      {/* Search */}
      <div className="relative w-full max-w-md mb-12">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShowResults(true);
          }}
          onFocus={() => setShowResults(true)}
          placeholder="Search members of Congress..."
          className="w-full px-4 py-3 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-civic-400 focus:border-civic-400 outline-none text-lg"
        />
        {showResults && results.length > 0 && (
          <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg">
            {results.map((p) => (
              <button
                key={p.person_id}
                onClick={() => {
                  router.push(`/people/${p.person_id}`);
                  setShowResults(false);
                }}
                className="w-full text-left px-4 py-3 hover:bg-civic-50 border-b border-gray-100 last:border-0"
              >
                <span className="font-medium">{p.full_name}</span>
                <span className="text-sm text-gray-500 ml-2">
                  {p.party} &middot; {p.state} &middot; {p.chamber}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Links */}
      <div className="flex gap-4 mb-12">
        <Link
          href="/browse"
          className="px-6 py-2 bg-civic-600 text-white rounded-lg hover:bg-civic-700 transition"
        >
          Browse Directory
        </Link>
        <Link
          href="/methodology"
          className="px-6 py-2 border border-civic-600 text-civic-600 rounded-lg hover:bg-civic-50 transition"
        >
          Methodology
        </Link>
      </div>

      {/* Status */}
      {status && (
        <div className="text-xs text-gray-400 space-y-1 text-center">
          <p>Dataset: {status.dataset_version}</p>
          <p>
            Last ingestion:{" "}
            {status.last_ingestion_run_at
              ? new Date(status.last_ingestion_run_at).toLocaleString()
              : "N/A (seed data)"}
          </p>
        </div>
      )}
    </div>
  );
}
