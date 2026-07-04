"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type PersonRow = {
  id?: string; // some endpoints may return this
  person_id?: string; // some endpoints may return this
  full_name?: string;
  name?: string;
  branch?: string;
  chamber?: "House" | "Senate" | string | null;
  office?: string | null;
  agency?: string | null;
  court?: string | null;
  state?: string;
  party?: string;
  service_start?: string;
  service_end?: string | null;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/api";

function getPersonId(p: PersonRow): string | null {
  return (p.id ?? p.person_id ?? null) as string | null;
}

function getPersonName(p: PersonRow): string {
  return p.full_name ?? p.name ?? "Unknown";
}

function getAffiliation(p: PersonRow): string {
  return (
    [p.branch, p.chamber, p.office, p.agency, p.court, p.state, p.party]
      .filter(Boolean)
      .join(" • ") || "Metadata unavailable"
  );
}

export default function BrowsePage() {
  const [people, setPeople] = useState<PersonRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // simple filters (MVP)
  const [chamber, setChamber] = useState<string>("");
  const [stateAbbr, setStateAbbr] = useState<string>("");
  const [party, setParty] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const params = new URLSearchParams();
        if (chamber) params.set("chamber", chamber);
        if (stateAbbr) params.set("state", stateAbbr);
        if (party) params.set("party", party);

        // Keep paging simple for now (MVP)
        params.set("page", "1");
        params.set("page_size", "50");

        const res = await fetch(`${API_BASE}/people?${params.toString()}`);
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(`Failed to load people (${res.status}). ${text}`);
        }

        const data = await res.json();

        // API might return {items:[...]} or [...]
        const items: PersonRow[] = Array.isArray(data) ? data : data.items ?? [];

        if (!cancelled) setPeople(items);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Failed to load people.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [chamber, stateAbbr, party]);

  const stats = useMemo(() => {
    const chambers = new Set<string>();
    const states = new Set<string>();
    const parties = new Set<string>();

    for (const p of people) {
      if (p.chamber) chambers.add(p.chamber);
      if (p.state) states.add(p.state);
      if (p.party) parties.add(p.party);
    }

    return {
      chambers: Array.from(chambers).sort(),
      states: Array.from(states).sort(),
      parties: Array.from(parties).sort(),
    };
  }, [people]);

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Browse Directory</h1>
        <p className="mt-1 text-sm text-gray-600">
          Filter currently available fixture officials by chamber, state, or party.
          Executive and judicial filters will be added as those sources are ingested.
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-gray-700">Chamber</span>
          <select
            className="rounded-md border px-3 py-2 text-sm"
            value={chamber}
            onChange={(e) => setChamber(e.target.value)}
          >
            <option value="">All</option>
            {/* Legislative fixture values; branch filters arrive with non-legislative ingestion. */}
            <option value="House">House</option>
            <option value="Senate">Senate</option>
            {/* In case seed includes variations */}
            {stats.chambers
              .filter((c) => c !== "House" && c !== "Senate")
              .map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-gray-700">State</span>
          <select
            className="rounded-md border px-3 py-2 text-sm"
            value={stateAbbr}
            onChange={(e) => setStateAbbr(e.target.value)}
          >
            <option value="">All</option>
            {stats.states.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-gray-700">Party</span>
          <select
            className="rounded-md border px-3 py-2 text-sm"
            value={party}
            onChange={(e) => setParty(e.target.value)}
          >
            <option value="">All</option>
            {stats.parties.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* States */}
      {loading && <div className="text-sm text-gray-600">Loading…</div>}

      {!loading && error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && people.length === 0 && (
        <div className="text-sm text-gray-600">No results.</div>
      )}

      {/* Results */}
      {!loading && !error && people.length > 0 && (
        <div className="grid grid-cols-1 gap-3">
          {people.map((p, idx) => {
            const pid = getPersonId(p);
            const name = getPersonName(p);

            // Guard: never create /people/undefined links
            if (!pid) {
              return (
                <div
                  key={`missing-${idx}`}
                  className="rounded-lg border bg-white p-4"
                >
                  <div className="font-medium">{name}</div>
                  <div className="mt-1 text-xs text-red-600">
                    Missing person id from API response (id/person_id). Check backend
                    response shape.
                  </div>
                </div>
              );
            }

            return (
              <Link
                key={pid}
                href={`/people/${pid}`}
                className="rounded-lg border bg-white p-4 hover:bg-gray-50"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="font-medium">{name}</div>
                    <div className="mt-1 text-xs text-gray-600">
                      {getAffiliation(p)}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500">
                    {p.service_start ? `Since ${p.service_start}` : ""}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </main>
  );
}
