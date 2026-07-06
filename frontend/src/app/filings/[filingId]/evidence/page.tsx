"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { FilingDetail, ParserArtifactItem } from "@/lib/types";
import { formatDateTime, StatusBadge } from "@/components/ProvenanceStatus";

export default function FilingEvidencePage({
  params,
}: {
  params: { filingId: string };
}) {
  const [filing, setFiling] = useState<FilingDetail | null>(null);
  const [artifacts, setArtifacts] = useState<ParserArtifactItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getFiling(params.filingId),
      api.getFilingArtifacts(params.filingId).catch(() => []),
    ])
      .then(([filingData, evidence]) => {
        setFiling(filingData);
        setArtifacts(evidence);
      })
      .catch(() => setFiling(null))
      .finally(() => setLoading(false));
  }, [params.filingId]);

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!filing) return <p className="text-red-500">Filing not found.</p>;

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold">Filing Evidence</h1>
      <p className="mt-1 break-all text-sm text-gray-500">{filing.id}</p>

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <div className="flex items-start justify-between gap-4">
          <h2 className="font-semibold text-gray-800">Filing Provenance</h2>
          <StatusBadge tone={filing.provenance_complete ? "complete" : "attention"}>
            {filing.provenance_complete ? "Complete" : "Incomplete"}
          </StatusBadge>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-gray-500">Type</dt>
            <dd className="mt-1">{filing.filing_type}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Filed</dt>
            <dd className="mt-1">{filing.filed_date}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Retrieved</dt>
            <dd className="mt-1">{formatDateTime(filing.retrieved_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Raw document</dt>
            <dd className="mt-1">
              {filing.raw_document_id ? (
                <Link
                  href={`/raw-documents/${filing.raw_document_id}`}
                  className="text-civic-700 underline"
                >
                  View raw document
                </Link>
              ) : (
                "Not linked"
              )}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-gray-500">Source URL</dt>
            <dd className="mt-1 break-all">
              <a
                href={filing.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-civic-700 underline"
              >
                {filing.source_url}
              </a>
            </dd>
          </div>
        </dl>
      </section>

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="font-semibold text-gray-800">Parser Evidence</h2>
        {artifacts.length === 0 ? (
          <p className="mt-3 text-sm text-gray-500">No parser artifacts linked.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {artifacts.map((artifact) => (
              <div key={artifact.id} className="rounded-md border border-gray-100 p-3 text-sm">
                <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                  <span>{artifact.artifact_type}</span>
                  <span>{artifact.source_id}</span>
                  {artifact.trade_id ? <span>trade {artifact.trade_id}</span> : null}
                </div>
                <pre className="mt-2 max-h-48 overflow-auto rounded bg-gray-50 p-3 text-xs">
                  {JSON.stringify(artifact.parser_output, null, 2)}
                </pre>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
