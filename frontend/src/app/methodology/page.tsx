"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type {
  MethodologyResponse,
  OfficialSourcesResponse,
  SourceCompletenessResponse,
} from "@/lib/types";

export default function MethodologyPage() {
  const [data, setData] = useState<MethodologyResponse | null>(null);
  const [sources, setSources] = useState<OfficialSourcesResponse | null>(null);
  const [completeness, setCompleteness] =
    useState<SourceCompletenessResponse | null>(null);
  const [sourceBranch, setSourceBranch] = useState("");
  const [sourceReadiness, setSourceReadiness] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getMethodology(), api.getSources(), api.getSourceCompleteness()])
      .then(([methodology, sourceData, completenessData]) => {
        setData(methodology);
        setSources(sourceData);
        setCompleteness(completenessData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!data) return <p className="text-red-500">Failed to load methodology.</p>;

  const completenessBySource = new Map(
    completeness?.sources.map((item) => [item.source_id, item]) ?? []
  );
  const filteredSources =
    sources?.sources.filter((source) => {
      const item = completenessBySource.get(source.id);
      const branchOk = !sourceBranch || source.branch === sourceBranch;
      const readinessOk =
        !sourceReadiness ||
        (sourceReadiness === "ready" && item?.missing_capabilities.length === 0) ||
        (sourceReadiness === "missing" && (item?.missing_capabilities.length ?? 0) > 0);
      return branchOk && readinessOk;
    }) ?? [];

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold mb-6">Methodology</h1>

      <div className="space-y-6">
        {data.blocks.map((block, i) => (
          <section key={i} className="bg-white border border-gray-200 rounded-lg p-5">
            <h2 className="text-lg font-semibold text-civic-700 mb-2">
              {block.title}
            </h2>
            <p className="text-sm text-gray-700 leading-relaxed">
              {block.content}
            </p>
          </section>
        ))}
      </div>

      <div className="mt-8 bg-civic-50 border border-civic-200 rounded-lg p-5">
        <h2 className="text-lg font-semibold text-civic-700 mb-3">
          Key Rules
        </h2>
        <ul className="space-y-2">
          {data.key_rules.map((rule, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
              <span className="text-civic-500 font-bold mt-0.5">•</span>
              {rule}
            </li>
          ))}
        </ul>
      </div>

      {sources ? (
        <section className="mt-8">
          <h2 className="text-lg font-semibold text-civic-700 mb-3">
            Official Source Intake
          </h2>
          <div className="mb-4 grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-gray-700">Branch</span>
              <select
                className="rounded-md border px-3 py-2 text-sm"
                value={sourceBranch}
                onChange={(e) => setSourceBranch(e.target.value)}
              >
                <option value="">All</option>
                <option value="Legislative">Legislative</option>
                <option value="Executive">Executive</option>
                <option value="Judicial">Judicial</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-gray-700">Readiness</span>
              <select
                className="rounded-md border px-3 py-2 text-sm"
                value={sourceReadiness}
                onChange={(e) => setSourceReadiness(e.target.value)}
              >
                <option value="">All</option>
                <option value="missing">Missing capabilities</option>
                <option value="ready">No missing capabilities</option>
              </select>
            </label>
          </div>
          <div className="space-y-4">
            {filteredSources.map((source) => {
              const item = completenessBySource.get(source.id);
              return (
                <article
                  key={source.id}
                  className="bg-white border border-gray-200 rounded-lg p-5"
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h3 className="font-semibold text-gray-900">
                        {source.name}
                      </h3>
                      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                        {source.branch}
                        {source.chamber ? ` / ${source.chamber}` : ""}
                      </p>
                      <p className="mt-2 text-sm text-gray-600">
                        {source.records_scope}
                      </p>
                    </div>
                    <span className="inline-flex w-fit rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">
                      {source.ingestion_status}
                    </span>
                  </div>

                  <div className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
                    <a
                      href={source.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-civic-700 underline break-all"
                    >
                      Source home
                    </a>
                    {source.search_url ? (
                      <a
                        href={source.search_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-civic-700 underline break-all"
                      >
                        Search entry point
                      </a>
                    ) : null}
                  </div>

                  {item ? (
                    <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-3">
                      <div>
                        <dt className="text-gray-500">Raw documents</dt>
                        <dd className="mt-1 font-medium text-gray-800">
                          {item.raw_document_count}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-gray-500">Filings</dt>
                        <dd className="mt-1 font-medium text-gray-800">
                          {item.filing_count}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-gray-500">Missing</dt>
                        <dd className="mt-1 font-medium text-gray-800">
                          {item.missing_capabilities.length || "None"}
                        </dd>
                      </div>
                    </dl>
                  ) : null}

                  <p className="mt-4 text-xs leading-relaxed text-gray-600">
                    {source.rights_note}
                  </p>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
