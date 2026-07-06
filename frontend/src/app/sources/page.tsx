"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { OfficialSourcesResponse, SourceCompletenessResponse } from "@/lib/types";
import { StatusBadge } from "@/components/ProvenanceStatus";

export default function SourcesPage() {
  const [sources, setSources] = useState<OfficialSourcesResponse | null>(null);
  const [completeness, setCompleteness] =
    useState<SourceCompletenessResponse | null>(null);
  const [branch, setBranch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getSources(), api.getSourceCompleteness()])
      .then(([sourceData, completenessData]) => {
        setSources(sourceData);
        setCompleteness(completenessData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const completenessBySource = useMemo(
    () => new Map(completeness?.sources.map((item) => [item.source_id, item]) ?? []),
    [completeness]
  );

  const visibleSources =
    sources?.sources.filter((source) => !branch || source.branch === branch) ?? [];

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!sources) return <p className="text-red-500">Failed to load sources.</p>;

  return (
    <div>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Source Readiness</h1>
          <p className="mt-1 max-w-2xl text-sm text-gray-600">
            Official-source intake state by branch. Counts reflect archived raw
            documents and normalized filings currently visible to the backend.
          </p>
        </div>
        <label className="flex min-w-48 flex-col gap-1">
          <span className="text-xs font-medium text-gray-700">Branch</span>
          <select
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
            className="rounded-md border px-3 py-2 text-sm"
          >
            <option value="">All</option>
            <option value="Legislative">Legislative</option>
            <option value="Executive">Executive</option>
            <option value="Judicial">Judicial</option>
          </select>
        </label>
      </div>

      <div className="grid gap-4">
        {visibleSources.map((source) => {
          const item = completenessBySource.get(source.id);
          const ready = item ? item.missing_capabilities.length === 0 : false;

          return (
            <article key={source.id} className="rounded-lg border border-gray-200 bg-white p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="font-semibold text-gray-900">{source.name}</h2>
                  <p className="mt-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                    {source.branch}
                    {source.chamber ? ` / ${source.chamber}` : ""}
                  </p>
                  <p className="mt-2 text-sm text-gray-600">{source.records_scope}</p>
                </div>
                <StatusBadge tone={ready ? "complete" : "attention"}>
                  {ready ? "Ready" : "Needs intake"}
                </StatusBadge>
              </div>

              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-gray-500">Raw documents</dt>
                  <dd className="mt-1 font-medium">{item?.raw_document_count ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-gray-500">Filings</dt>
                  <dd className="mt-1 font-medium">{item?.filing_count ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-gray-500">Requirements</dt>
                  <dd className="mt-1 font-medium">
                    {item?.provenance_requirements_count ?? source.provenance_requirements.length}
                  </dd>
                </div>
                <div>
                  <dt className="text-gray-500">Missing</dt>
                  <dd className="mt-1 font-medium">
                    {item?.missing_capabilities.length ?? "Unknown"}
                  </dd>
                </div>
              </dl>

              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-gray-500">Access mode</dt>
                  <dd className="mt-1 font-medium">{source.access_mode ?? "Not specified"}</dd>
                </div>
                <div>
                  <dt className="text-gray-500">Public sample</dt>
                  <dd className="mt-1 font-medium">
                    {source.public_sample_url ? "Configured" : "Not configured"}
                  </dd>
                </div>
              </dl>

              {item && item.missing_capabilities.length > 0 ? (
                <ul className="mt-4 list-disc space-y-1 pl-5 text-xs text-gray-600">
                  {item.missing_capabilities.map((missing) => (
                    <li key={missing}>{missing}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
