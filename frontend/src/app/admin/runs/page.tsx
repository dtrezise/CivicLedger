"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { IngestionRunItem } from "@/lib/types";
import { formatDateTime, StatusBadge } from "@/components/ProvenanceStatus";

export default function AdminRunsPage() {
  const [runs, setRuns] = useState<IngestionRunItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listIngestionRuns()
      .then((response) => setRuns(response.items))
      .catch(() => setRuns([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-400">Loading...</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold">Source Runs</h1>
      <p className="mt-1 text-sm text-gray-600">
        Ingestion history for manual uploads, source-client downloads, and future scheduled runs.
      </p>

      <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Started</th>
              <th className="px-4 py-3">Completed</th>
              <th className="px-4 py-3">Parser</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="px-4 py-3">
                  <p className="font-medium text-gray-900">{run.source_name}</p>
                  <p className="mt-1 break-all text-xs text-gray-500">{run.id}</p>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge tone={run.status === "completed" ? "complete" : "attention"}>
                    {run.status}
                  </StatusBadge>
                </td>
                <td className="px-4 py-3">{formatDateTime(run.started_at)}</td>
                <td className="px-4 py-3">{run.completed_at ? formatDateTime(run.completed_at) : "-"}</td>
                <td className="px-4 py-3">{run.parser_version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
