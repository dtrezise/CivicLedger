"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ParserArtifactItem, RawDocumentDetail } from "@/lib/types";
import { formatDateTime, StatusBadge } from "@/components/ProvenanceStatus";

export default function RawDocumentPage({
  params,
}: {
  params: { rawDocumentId: string };
}) {
  const [document, setDocument] = useState<RawDocumentDetail | null>(null);
  const [artifacts, setArtifacts] = useState<ParserArtifactItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getRawDocument(params.rawDocumentId),
      api.getRawDocumentArtifacts(params.rawDocumentId).catch(() => []),
    ])
      .then(([rawDocument, evidence]) => {
        setDocument(rawDocument);
        setArtifacts(evidence);
      })
      .catch(() => setDocument(null))
      .finally(() => setLoading(false));
  }, [params.rawDocumentId]);

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!document) return <p className="text-red-500">Raw document not found.</p>;

  return (
    <div className="max-w-4xl">
      <div className="mb-4">
        <Link href="/methodology" className="text-sm text-civic-600 hover:underline">
          &larr; Methodology
        </Link>
      </div>

      <h1 className="text-2xl font-bold">Raw Document</h1>
      <p className="mt-1 break-all text-sm text-gray-500">{document.id}</p>

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <div className="flex items-start justify-between gap-4">
          <h2 className="font-semibold text-gray-800">Source Metadata</h2>
          <StatusBadge tone={document.provenance_complete ? "complete" : "attention"}>
            {document.provenance_complete ? "Complete" : "Incomplete"}
          </StatusBadge>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-gray-500">Retrieval source</dt>
            <dd className="mt-1 font-mono">{document.retrieval_source}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Retrieved</dt>
            <dd className="mt-1">{formatDateTime(document.retrieved_at)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Content type</dt>
            <dd className="mt-1">{document.content_type}</dd>
          </div>
          <div>
            <dt className="text-gray-500">File hash</dt>
            <dd className="mt-1 break-all font-mono text-xs">{document.file_hash}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-gray-500">Source URL</dt>
            <dd className="mt-1 break-all">
              <a
                href={document.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-civic-700 underline"
              >
                {document.source_url}
              </a>
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-gray-500">Storage URI</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {document.storage_uri ?? "Not provided"}
            </dd>
          </div>
        </dl>
      </section>

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="font-semibold text-gray-800">Parser Artifacts</h2>
        {artifacts.length === 0 ? (
          <p className="mt-3 text-sm text-gray-500">No parser artifacts linked.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {artifacts.map((artifact) => (
              <div key={artifact.id} className="rounded-md border border-gray-100 p-3 text-sm">
                <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                  <span>{artifact.artifact_type}</span>
                  <span>{artifact.source_id}</span>
                  {artifact.filing_id ? (
                    <Link
                      href={`/filings/${artifact.filing_id}/evidence`}
                      className="text-civic-700 underline"
                    >
                      Filing evidence
                    </Link>
                  ) : null}
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
