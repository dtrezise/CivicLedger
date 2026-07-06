"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DuplicateReportResponse } from "@/lib/types";
import { StatusBadge } from "@/components/ProvenanceStatus";

export default function QualityPage() {
  const [report, setReport] = useState<DuplicateReportResponse | null>(null);

  useEffect(() => {
    api.getDuplicateReport().then(setReport).catch(() => setReport(null));
  }, []);

  if (!report) return <p className="text-gray-400">Loading...</p>;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Data Quality</h1>
          <p className="mt-1 text-sm text-gray-600">Duplicate filings and trades that need review.</p>
        </div>
        <StatusBadge
          tone={report.trade_groups.length || report.filing_groups.length ? "attention" : "complete"}
        >
          {report.trade_groups.length + report.filing_groups.length} groups
        </StatusBadge>
      </div>

      <section>
        <h2 className="font-semibold text-gray-900">Duplicate Trades</h2>
        <div className="mt-3 space-y-3">
          {report.trade_groups.length === 0 ? (
            <p className="text-sm text-gray-500">No duplicate trade groups detected.</p>
          ) : (
            report.trade_groups.map((group) => (
              <article key={group.duplicate_key} className="rounded-lg border border-gray-200 bg-white p-4 text-sm">
                <p className="font-medium">{group.asset_display_name}</p>
                <p className="mt-1 text-gray-500">
                  {group.trade_date} / {group.action} / {group.value_range_label}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {group.trade_ids.map((id) => (
                    <Link key={id} href={`/trades/${id}`} className="text-civic-700 underline">
                      {id}
                    </Link>
                  ))}
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="font-semibold text-gray-900">Duplicate Filings</h2>
        <div className="mt-3 space-y-3">
          {report.filing_groups.length === 0 ? (
            <p className="text-sm text-gray-500">No duplicate filing groups detected.</p>
          ) : (
            report.filing_groups.map((group) => (
              <article key={group.duplicate_key} className="rounded-lg border border-gray-200 bg-white p-4 text-sm">
                <p className="font-medium">{group.filing_type}</p>
                <p className="mt-1 text-gray-500">{group.filed_date}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {group.filing_ids.map((id) => (
                    <Link key={id} href={`/filings/${id}/evidence`} className="text-civic-700 underline">
                      {id}
                    </Link>
                  ))}
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
