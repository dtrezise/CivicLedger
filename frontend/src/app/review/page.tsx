"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { ParserArtifactItem } from "@/lib/types";
import { StatusBadge } from "@/components/ProvenanceStatus";

type FormState = {
  reviewer: string;
  person_name: string;
  branch: string;
  chamber: string;
  state: string;
  party: string;
  office: string;
  agency: string;
  court: string;
};

const initialForm: FormState = {
  reviewer: "",
  person_name: "",
  branch: "Legislative",
  chamber: "",
  state: "",
  party: "",
  office: "",
  agency: "",
  court: "",
};

export default function ReviewPage() {
  const [previews, setPreviews] = useState<ParserArtifactItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [form, setForm] = useState<FormState>(initialForm);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .listParserPreviews()
      .then((response) => {
        setPreviews(response.items);
        if (response.items[0]) {
          setSelectedId(response.items[0].id);
        }
      })
      .catch(() => setMessage("Failed to load parser previews."))
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(
    () => previews.find((preview) => preview.id === selectedId),
    [previews, selectedId]
  );

  useEffect(() => {
    if (!selected) return;
    const output = selected.parser_output;
    setForm((current) => ({
      ...current,
      person_name:
        typeof output.filer_name === "string" ? output.filer_name : current.person_name,
      branch:
        typeof output.output === "object" &&
        output.output &&
        "branch" in output.output &&
        typeof output.output.branch === "string"
          ? output.output.branch
          : current.branch,
    }));
  }, [selected]);

  async function promote() {
    if (!selected) return;
    setMessage("");
    try {
      const response = await api.promoteParserPreview(selected.id, {
        reviewer: form.reviewer,
        person_name: form.person_name,
        branch: form.branch,
        chamber: form.chamber || undefined,
        state: form.state || undefined,
        party: form.party || undefined,
        office: form.office || undefined,
        agency: form.agency || undefined,
        court: form.court || undefined,
      });
      setMessage(`Promoted filing ${response.filing_id} with ${response.trade_count} trades.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Promotion failed.");
    }
  }

  if (loading) return <p className="text-gray-400">Loading...</p>;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section>
        <div className="mb-5">
          <h1 className="text-2xl font-bold">Review Queue</h1>
          <p className="mt-1 max-w-2xl text-sm text-gray-600">
            Parser previews stay out of public filings until a reviewer promotes
            them into normalized records.
          </p>
        </div>

        <div className="space-y-3">
          {previews.length === 0 ? (
            <p className="text-sm text-gray-500">No parser previews are waiting.</p>
          ) : (
            previews.map((preview) => {
              const selectedPreview = preview.id === selectedId;
              const count = preview.parser_output.normalized_record_count;
              const warnings = Array.isArray(preview.parser_output.warnings)
                ? preview.parser_output.warnings
                : [];
              return (
                <button
                  key={preview.id}
                  onClick={() => setSelectedId(preview.id)}
                  className={`block w-full rounded-lg border bg-white p-4 text-left ${
                    selectedPreview ? "border-civic-500" : "border-gray-200"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium text-gray-900">
                        {String(preview.parser_output.filer_name || "Unknown filer")}
                      </p>
                      <p className="mt-1 text-xs text-gray-500">{preview.source_id}</p>
                    </div>
                    <StatusBadge tone={warnings.length ? "attention" : "complete"}>
                      {String(count ?? 0)} rows
                    </StatusBadge>
                  </div>
                  <p className="mt-2 break-all text-xs text-gray-500">{preview.id}</p>
                </button>
              );
            })
          )}
        </div>
      </section>

      <aside className="rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="font-semibold text-gray-900">Promote Preview</h2>
        {selected ? (
          <>
            <Link
              href={`/raw-documents/${selected.raw_document_id}`}
              className="mt-2 inline-block text-sm text-civic-700 underline"
            >
              View raw document
            </Link>
            <div className="mt-4 space-y-3">
              {[
                ["Reviewer", "reviewer"],
                ["Person", "person_name"],
                ["Chamber", "chamber"],
                ["State", "state"],
                ["Party", "party"],
                ["Office", "office"],
                ["Agency", "agency"],
                ["Court", "court"],
              ].map(([label, key]) => (
                <label key={key} className="block text-sm">
                  <span className="text-xs font-medium text-gray-600">{label}</span>
                  <input
                    value={form[key as keyof FormState]}
                    onChange={(event) =>
                      setForm({ ...form, [key]: event.target.value })
                    }
                    className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                  />
                </label>
              ))}
              <label className="block text-sm">
                <span className="text-xs font-medium text-gray-600">Branch</span>
                <select
                  value={form.branch}
                  onChange={(event) => setForm({ ...form, branch: event.target.value })}
                  className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
                >
                  <option>Legislative</option>
                  <option>Executive</option>
                  <option>Judicial</option>
                </select>
              </label>
              <button
                onClick={promote}
                className="w-full rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white"
              >
                Promote
              </button>
              {message ? <p className="text-sm text-gray-600">{message}</p> : null}
            </div>
          </>
        ) : (
          <p className="mt-3 text-sm text-gray-500">Select a preview to review.</p>
        )}
      </aside>
    </div>
  );
}
