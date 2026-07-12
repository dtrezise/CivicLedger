"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/ProvenanceStatus";
import { api } from "@/lib/api";
import type {
  ParserArtifactItem,
  RelationshipCandidate,
  RelationshipCandidateListResponse,
  RelationshipDecision,
  RelationshipSort,
  RelationshipStatus,
} from "@/lib/types";

type ReviewView = "relationships" | "parser";

type ParserFormState = {
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "/api";

const initialParserForm: ParserFormState = {
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

const statusOptions: Array<{ value: RelationshipStatus | ""; label: string }> = [
  { value: "candidate", label: "Candidate" },
  { value: "accepted", label: "Accepted" },
  { value: "narrowed", label: "Narrowed" },
  { value: "rejected", label: "Rejected" },
  { value: "superseded", label: "Superseded" },
  { value: "", label: "All statuses" },
];

const decisionOptions: Array<{ value: RelationshipDecision; label: string }> = [
  { value: "accept", label: "Accept" },
  { value: "narrow", label: "Narrow" },
  { value: "reject", label: "Reject" },
  { value: "supersede", label: "Supersede" },
];

async function fetchRelationshipAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch {
      // The status code remains useful when an upstream returns a non-JSON error.
    }
    throw new Error(detail || `Request failed (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

function formatDate(value: string) {
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function formatTimestamp(value: string | null) {
  if (!value) return "Timestamp unavailable";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function formatEnum(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDayDistance(days: number) {
  if (days === 0) return "Same day";
  const count = Math.abs(days);
  return `${count} day${count === 1 ? "" : "s"} ${days < 0 ? "before" : "after"}`;
}

function formatReason(reason: string | Record<string, unknown>) {
  if (typeof reason === "string") return reason;
  for (const key of ["reason", "label", "description", "value"]) {
    if (typeof reason[key] === "string") return String(reason[key]);
  }
  const parts = Object.entries(reason).map(([key, value]) => {
    const displayValue =
      value !== null && typeof value === "object" ? JSON.stringify(value) : String(value);
    return `${formatEnum(key)}: ${displayValue}`;
  });
  return parts.join("; ") || "Evidence reason recorded";
}

function statusTone(status: RelationshipStatus): "neutral" | "complete" | "attention" | "fixture" {
  if (status === "accepted") return "complete";
  if (status === "candidate" || status === "narrowed") return "attention";
  if (status === "superseded") return "fixture";
  return "neutral";
}

function RelationshipCandidateReview() {
  const [queue, setQueue] = useState<RelationshipCandidateListResponse>({
    items: [],
    page: 1,
    page_size: 25,
    total: 0,
    sort: "priority",
  });
  const [status, setStatus] = useState<RelationshipStatus | "">("candidate");
  const [evidenceTier, setEvidenceTier] = useState("");
  const [eventType, setEventType] = useState("");
  const [maxDays, setMaxDays] = useState("");
  const [minRank, setMinRank] = useState("");
  const [reviewHistory, setReviewHistory] = useState("");
  const [sort, setSort] = useState<RelationshipSort>("priority");
  const [pageSize, setPageSize] = useState(25);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [decision, setDecision] = useState<RelationshipDecision>("accept");
  const [reviewer, setReviewer] = useState("");
  const [evidenceNote, setEvidenceNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadQueue() {
      setLoading(true);
      setLoadError("");
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        sort,
      });
      if (status) params.set("status", status);
      if (evidenceTier.trim()) params.set("evidence_tier", evidenceTier.trim());
      if (eventType.trim()) params.set("event_type", eventType.trim());
      if (maxDays) params.set("max_abs_days", maxDays);
      if (minRank) params.set("min_internal_rank", minRank);
      if (reviewHistory) params.set("has_reviews", reviewHistory);
      if (query.length >= 2) params.set("q", query);
      try {
        const response = await fetchRelationshipAPI<RelationshipCandidateListResponse>(
          `/review/relationship-candidates?${params.toString()}`
        );
        if (cancelled) return;
        setQueue(response);
        setSelectedId((current) =>
          response.items.some((candidate) => candidate.id === current)
            ? current
            : response.items[0]?.id || ""
        );
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : "Failed to load candidates.");
        setQueue({ items: [], page, page_size: pageSize, total: 0, sort });
        setSelectedId("");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadQueue();
    return () => {
      cancelled = true;
    };
  }, [evidenceTier, eventType, maxDays, minRank, page, pageSize, query, reloadToken, reviewHistory, sort, status]);

  const selected = useMemo(
    () => queue.items.find((candidate) => candidate.id === selectedId),
    [queue.items, selectedId]
  );
  const totalPages = Math.max(1, Math.ceil(queue.total / queue.page_size));
  const canSubmit = Boolean(selected && reviewer.trim() && evidenceNote.trim() && !saving);

  async function submitDecision() {
    if (!selected || !canSubmit) return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await fetchRelationshipAPI<RelationshipCandidate>(
        `/review/relationship-candidates/${selected.id}/decisions`,
        {
          method: "POST",
          body: JSON.stringify({
            decision,
            reviewer,
            evidence_note: evidenceNote,
            expected_status: selected.review_status,
          }),
        }
      );
      setEvidenceNote("");
      setMessageIsError(false);
      setMessage(
        `${formatEnum(updated.review_status)} by ${updated.reviews.at(-1)?.reviewer || reviewer}.`
      );
      setReloadToken((current) => current + 1);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Decision failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <section className="min-w-0">
        <form
          className="mb-4 grid gap-3 border-b border-gray-200 pb-4 sm:grid-cols-2 xl:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(queryInput.trim());
            setPage(1);
          }}
        >
          <label className="block text-sm sm:col-span-2 xl:col-span-4">
            <span className="text-xs font-medium text-gray-600">Search official, asset, ticker, or event</span>
            <span className="mt-1 flex gap-2">
              <input
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                minLength={2}
                maxLength={200}
                placeholder="Search review queue"
                className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
              <button type="submit" className="rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white">
                Search
              </button>
            </span>
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Status</span>
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as RelationshipStatus | "");
                setPage(1);
                setMessage("");
              }}
              className="mt-1 block min-w-44 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              {statusOptions.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Evidence tier</span>
            <input
              value={evidenceTier}
              onChange={(event) => { setEvidenceTier(event.target.value); setPage(1); }}
              placeholder="All tiers"
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Event type</span>
            <input
              value={eventType}
              onChange={(event) => { setEventType(event.target.value); setPage(1); }}
              placeholder="All event types"
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Maximum timing distance</span>
            <select
              value={maxDays}
              onChange={(event) => { setMaxDays(event.target.value); setPage(1); }}
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">Any distance</option>
              <option value="7">7 days</option>
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="180">180 days</option>
              <option value="365">365 days</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Minimum internal rank</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={minRank}
              onChange={(event) => { setMinRank(event.target.value); setPage(1); }}
              placeholder="Any rank"
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Review history</span>
            <select
              value={reviewHistory}
              onChange={(event) => { setReviewHistory(event.target.value); setPage(1); }}
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">Any</option>
              <option value="false">Not reviewed</option>
              <option value="true">Has history</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Sort</span>
            <select
              value={sort}
              onChange={(event) => { setSort(event.target.value as RelationshipSort); setPage(1); }}
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              <option value="priority">Evidence priority</option>
              <option value="newest">Newest queued</option>
              <option value="oldest">Oldest queued</option>
              <option value="event_date">Newest event</option>
              <option value="trade_date">Newest trade</option>
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-xs font-medium text-gray-600">Rows per page</span>
            <select
              value={pageSize}
              onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}
              className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
            >
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
          <div className="flex items-end justify-between gap-3 sm:col-span-2 xl:col-span-4">
            <p className="text-sm tabular-nums text-gray-500">
              {queue.total} {queue.total === 1 ? "candidate" : "candidates"}
            </p>
            <button
              type="button"
              onClick={() => {
                setStatus("candidate"); setEvidenceTier(""); setEventType(""); setMaxDays("");
                setMinRank(""); setReviewHistory(""); setSort("priority"); setQueryInput(""); setQuery(""); setPage(1);
              }}
              className="text-sm font-medium text-civic-700 hover:underline"
            >
              Clear filters
            </button>
          </div>
        </form>

        {message ? (
          <p
            aria-live="polite"
            className={`mb-4 border-l-2 pl-3 text-sm ${
              messageIsError
                ? "border-red-500 text-red-700"
                : "border-emerald-500 text-emerald-700"
            }`}
          >
            {message}
          </p>
        ) : null}

        {loading ? <p className="text-sm text-gray-500">Loading candidates...</p> : null}
        {loadError ? (
          <p className="border-l-2 border-red-500 pl-3 text-sm text-red-700">{loadError}</p>
        ) : null}
        {!loading && !loadError && queue.items.length === 0 ? (
          <p className="text-sm text-gray-500">No candidates match this status.</p>
        ) : null}

        <div className="space-y-2">
          {queue.items.map((candidate) => {
            const isSelected = candidate.id === selectedId;
            return (
              <button
                key={candidate.id}
                type="button"
                onClick={() => {
                  setSelectedId(candidate.id);
                  setMessage("");
                  setEvidenceNote("");
                }}
                className={`w-full rounded-lg border bg-white p-4 text-left transition-colors ${
                  isSelected
                    ? "border-civic-500 ring-1 ring-civic-200"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-900">{candidate.person_name}</p>
                    <p className="mt-1 break-words text-sm text-gray-700">
                      {formatEnum(candidate.action)} | {candidate.asset_display_name}
                      {candidate.ticker ? ` (${candidate.ticker})` : ""}
                    </p>
                  </div>
                  <StatusBadge tone={statusTone(candidate.review_status)}>
                    {formatEnum(candidate.review_status)}
                  </StatusBadge>
                </div>
                <p className="mt-3 break-words text-sm text-gray-600">{candidate.event_label}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
                  <span>{formatDate(candidate.trade_date)}</span>
                  <span>{formatDayDistance(candidate.days_from_event)}</span>
                  <span>{formatEnum(candidate.evidence_tier)}</span>
                  {candidate.internal_rank !== null ? <span>Rank {candidate.internal_rank}</span> : null}
                  <span>{candidate.reviews.length} review{candidate.reviews.length === 1 ? "" : "s"}</span>
                </div>
              </button>
            );
          })}
        </div>

        {queue.total > queue.page_size ? (
          <div className="mt-5 flex items-center justify-between border-t border-gray-200 pt-4">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1 || loading}
              className="text-sm font-medium text-civic-700 disabled:text-gray-400"
            >
              Previous
            </button>
            <span className="text-xs tabular-nums text-gray-500">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages || loading}
              className="text-sm font-medium text-civic-700 disabled:text-gray-400"
            >
              Next
            </button>
          </div>
        ) : null}
      </section>

      <aside className="min-w-0 border-t border-gray-200 pt-6 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
        {selected ? (
          <div>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase text-gray-500">Relationship candidate</p>
                <h2 className="mt-1 break-words text-lg font-semibold text-gray-900">
                  {selected.event_label}
                </h2>
              </div>
              <StatusBadge tone={statusTone(selected.review_status)}>
                {formatEnum(selected.review_status)}
              </StatusBadge>
            </div>

            <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 border-y border-gray-200 py-4 text-sm">
              <div>
                <dt className="text-xs text-gray-500">Official</dt>
                <dd className="mt-1 break-words font-medium text-gray-900">{selected.person_name}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Trade date</dt>
                <dd className="mt-1 text-gray-800">{formatDate(selected.trade_date)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Asset</dt>
                <dd className="mt-1 break-words text-gray-800">{selected.asset_display_name}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Event date</dt>
                <dd className="mt-1 text-gray-800">{formatDate(selected.event_date)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Timing</dt>
                <dd className="mt-1 text-gray-800">{formatDayDistance(selected.days_from_event)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500">Value range</dt>
                <dd className="mt-1 break-words text-gray-800">{selected.value_range_label}</dd>
              </div>
            </dl>

            <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm font-medium">
              <Link href={`/trades/${selected.trade_id}`} className="text-civic-700 hover:underline">
                Trade record
              </Link>
              <Link
                href={`/events/${selected.event_id}/sources`}
                className="text-civic-700 hover:underline"
              >
                Event sources
              </Link>
            </div>

            <section className="mt-6">
              <h3 className="text-sm font-semibold text-gray-900">Candidate evidence</h3>
              {selected.relationship_reasons.length ? (
                <ul className="mt-3 space-y-2 border-l-2 border-gray-200 pl-3 text-sm text-gray-700">
                  {selected.relationship_reasons.map((reason, index) => (
                    <li key={`${selected.id}-reason-${index}`} className="break-words">
                      {formatReason(reason)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-gray-500">No relationship reasons recorded.</p>
              )}
              <p className="mt-3 text-xs text-gray-500">
                {formatEnum(selected.evidence_tier)} | {selected.methodology_version} | queued {formatTimestamp(selected.created_at)}
              </p>
            </section>

            <section className="mt-6 border-t border-gray-200 pt-5">
              <h3 className="text-sm font-semibold text-gray-900">Decision</h3>
              <div className="mt-3 space-y-3">
                <label className="block text-sm">
                  <span className="text-xs font-medium text-gray-600">Decision</span>
                  <select
                    value={decision}
                    onChange={(event) => setDecision(event.target.value as RelationshipDecision)}
                    className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                  >
                    {decisionOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-sm">
                  <span className="text-xs font-medium text-gray-600">Reviewer</span>
                  <input
                    value={reviewer}
                    onChange={(event) => setReviewer(event.target.value)}
                    maxLength={200}
                    autoComplete="name"
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
                <label className="block text-sm">
                  <span className="text-xs font-medium text-gray-600">Evidence note</span>
                  <textarea
                    value={evidenceNote}
                    onChange={(event) => setEvidenceNote(event.target.value)}
                    maxLength={5000}
                    rows={4}
                    className="mt-1 w-full resize-y rounded-md border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
                <button
                  type="button"
                  onClick={submitDecision}
                  disabled={!canSubmit}
                  className="w-full rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  {saving ? "Recording..." : "Record decision"}
                </button>
              </div>
            </section>

            <section className="mt-6 border-t border-gray-200 pt-5">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-gray-900">Decision history</h3>
                <span className="text-xs tabular-nums text-gray-500">{selected.reviews.length}</span>
              </div>
              {selected.reviews.length ? (
                <ol className="mt-3 divide-y divide-gray-200">
                  {[...selected.reviews].reverse().map((review) => (
                    <li key={review.id} className="py-3 first:pt-0">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-medium text-gray-900">
                          {formatEnum(review.decision)}
                        </p>
                        <time className="text-right text-xs text-gray-500">
                          {formatTimestamp(review.reviewed_at)}
                        </time>
                      </div>
                      <p className="mt-1 text-xs font-medium text-gray-600">{review.reviewer}</p>
                      <p className="mt-2 break-words text-sm text-gray-700">{review.evidence_note}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="mt-2 text-sm text-gray-500">No decisions recorded.</p>
              )}
            </section>
          </div>
        ) : (
          <p className="text-sm text-gray-500">Select a relationship candidate.</p>
        )}
      </aside>
    </div>
  );
}

function ParserPreviewReview() {
  const [previews, setPreviews] = useState<ParserArtifactItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [form, setForm] = useState<ParserFormState>(initialParserForm);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    api
      .listParserPreviews()
      .then((response) => {
        setPreviews(response.items);
        if (response.items[0]) setSelectedId(response.items[0].id);
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

  if (loading) return <p className="text-sm text-gray-500">Loading parser previews...</p>;

  const canPromote = Boolean(
    selected && form.reviewer.trim() && form.person_name.trim() && form.branch.trim()
  );
  const selectedWarnings = Array.isArray(selected?.parser_output.warnings)
    ? selected.parser_output.warnings
    : [];
  const selectedTransactions = Array.isArray(selected?.parser_output.transactions)
    ? selected.parser_output.transactions
    : [];

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <section>
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
                  type="button"
                  onClick={() => setSelectedId(preview.id)}
                  className={`block w-full rounded-lg border bg-white p-4 text-left ${
                    selectedPreview ? "border-civic-500 ring-1 ring-civic-200" : "border-gray-200"
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

      <aside className="border-t border-gray-200 pt-6 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
        <h2 className="font-semibold text-gray-900">Raw document review</h2>
        {selected ? (
          <>
            <div className="mt-3 grid gap-2 text-sm font-medium">
              <Link href={`/raw-documents/${selected.raw_document_id}`} className="text-civic-700 hover:underline">
                Raw document and artifacts
              </Link>
              <Link
                href={`/evidence?q=${encodeURIComponent(String(selected.raw_document_id))}`}
                className="text-civic-700 hover:underline"
              >
                Filing evidence trail
              </Link>
            </div>
            <div className="mt-4 border-y border-gray-200 py-3 text-xs text-gray-600">
              <p>{selectedTransactions.length} normalized rows detected.</p>
              {selectedWarnings.length ? (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-amber-800">
                  {selectedWarnings.slice(0, 3).map((warning) => (
                    <li key={String(warning)}>{String(warning)}</li>
                  ))}
                </ul>
              ) : null}
            </div>
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
                    value={form[key as keyof ParserFormState]}
                    onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                    className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                  />
                </label>
              ))}
              <label className="block text-sm">
                <span className="text-xs font-medium text-gray-600">Branch</span>
                <select
                  value={form.branch}
                  onChange={(event) => setForm({ ...form, branch: event.target.value })}
                  className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  <option>Legislative</option>
                  <option>Executive</option>
                  <option>Judicial</option>
                </select>
              </label>
              <button
                type="button"
                onClick={promote}
                disabled={!canPromote}
                className="w-full rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                Promote parsed rows
              </button>
              {message ? <p className="break-words text-sm text-gray-600">{message}</p> : null}
            </div>
          </>
        ) : (
          <p className="mt-3 text-sm text-gray-500">Select a preview to review.</p>
        )}
      </aside>
    </div>
  );
}

export default function ReviewPage() {
  const [view, setView] = useState<ReviewView>("relationships");

  return (
    <div>
      <div className="mb-6 border-b border-gray-200">
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
        <div className="mt-5 flex gap-6" role="tablist" aria-label="Review queue">
          <button
            type="button"
            role="tab"
            aria-selected={view === "relationships"}
            onClick={() => setView("relationships")}
            className={`border-b-2 pb-3 text-sm font-medium ${
              view === "relationships"
                ? "border-civic-600 text-civic-800"
                : "border-transparent text-gray-500 hover:text-gray-800"
            }`}
          >
            Relationship candidates
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={view === "parser"}
            onClick={() => setView("parser")}
            className={`border-b-2 pb-3 text-sm font-medium ${
              view === "parser"
                ? "border-civic-600 text-civic-800"
                : "border-transparent text-gray-500 hover:text-gray-800"
            }`}
          >
            Parser previews
          </button>
        </div>
      </div>

      {view === "relationships" ? <RelationshipCandidateReview /> : <ParserPreviewReview />}
    </div>
  );
}
