"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/ProvenanceStatus";
import { api } from "@/lib/api";
import type {
  ParserArtifactItem,
  RelationshipBulkReviewResponse,
  RelationshipCandidate,
  RelationshipCandidateListResponse,
  RelationshipDecision,
  RelationshipSort,
  RelationshipStatus,
  ReviewAssignment,
  ReviewFilterCriteria,
  ReviewSavedFilter,
  ReviewSessionSummary,
  ReviewerTelemetry,
} from "@/lib/types";

type ReviewView = "relationships" | "parser";

type BulkReviewTarget = {
  candidate_id: string;
  expected_status: RelationshipStatus;
  expected_revision: string;
};

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

function telemetryTone(status: string): "neutral" | "complete" | "attention" {
  if (status === "healthy") return "complete";
  if (status === "attention") return "attention";
  return "neutral";
}

function formatDuration(value: number | null) {
  if (value === null) return "Not observed";
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${(value / 60).toFixed(1)}m`;
}

function ReviewerTelemetryStrip() {
  const [telemetry, setTelemetry] = useState<ReviewerTelemetry | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchRelationshipAPI<ReviewerTelemetry>("/review/telemetry")
      .then((response) => {
        if (!cancelled) setTelemetry(response);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (failed) {
    return (
      <p className="mb-5 border-l-2 border-red-500 pl-3 text-sm text-red-700">
        Reviewer telemetry is unavailable.
      </p>
    );
  }
  if (!telemetry) {
    return <p className="mb-5 text-sm text-gray-500">Loading operational telemetry...</p>;
  }

  const driftSources = telemetry.data_drift.filter((row) => row.status !== "unchanged");
  return (
    <section className="mb-6 border-y border-gray-200 py-4" aria-label="Source refresh telemetry">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-gray-900">Source refresh telemetry</h2>
        <StatusBadge tone={telemetryTone(telemetry.status)}>
          {formatEnum(telemetry.status)}
        </StatusBadge>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-gray-500">Measured refreshes</dt>
          <dd className="mt-1 text-sm font-semibold tabular-nums text-gray-900">
            {telemetry.summary.measured_refresh_count}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">P95 duration</dt>
          <dd className="mt-1 text-sm font-semibold tabular-nums text-gray-900">
            {formatDuration(telemetry.refresh_duration.p95)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Recorded failures</dt>
          <dd className="mt-1 text-sm font-semibold tabular-nums text-gray-900">
            {telemetry.summary.source_failure_count}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-500">Aggregate drift</dt>
          <dd className="mt-1 text-sm font-semibold tabular-nums text-gray-900">
            {telemetry.summary.data_drift_count}
          </dd>
        </div>
      </dl>
      {telemetry.source_failures.length || driftSources.length ? (
        <details className="mt-3 border-t border-gray-100 pt-3 text-sm">
          <summary className="cursor-pointer font-medium text-civic-700">Review signals</summary>
          <ul className="mt-2 space-y-1 text-gray-700">
            {telemetry.source_failures.map((failure) => (
              <li key={`${failure.source_id}-${failure.source_artifact}-${failure.metric}`}>
                {formatEnum(failure.source_id)}: {failure.failure_count} {formatEnum(failure.metric)}
              </li>
            ))}
            {driftSources.map((drift) => (
              <li key={drift.source_id}>
                {formatEnum(drift.source_id)}: {formatEnum(drift.status)} ({drift.baseline_record_count ?? "n/a"} to{" "}
                {drift.current_record_count ?? "n/a"})
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
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
  const [bulkSelection, setBulkSelection] = useState<Record<string, BulkReviewTarget>>({});
  const [message, setMessage] = useState("");
  const [messageIsError, setMessageIsError] = useState(false);
  const [savedFilters, setSavedFilters] = useState<ReviewSavedFilter[]>([]);
  const [filterName, setFilterName] = useState("");
  const [sessions, setSessions] = useState<ReviewSessionSummary[]>([]);
  const [activeSession, setActiveSession] = useState<ReviewSessionSummary | null>(null);
  const [assignment, setAssignment] = useState<ReviewAssignment | null>(null);

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
        setBulkSelection((current) => {
          const next: Record<string, BulkReviewTarget> = {};
          response.items.forEach((candidate) => {
            if (current[candidate.id]) {
              next[candidate.id] = {
                candidate_id: candidate.id,
                expected_status: candidate.review_status,
                expected_revision: candidate.review_revision,
              };
            }
          });
          return next;
        });
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
  const bulkTargets = Object.values(bulkSelection);
  const canSubmitBulk = Boolean(
    bulkTargets.length && reviewer.trim() && evidenceNote.trim() && !saving
  );
  const allPageSelected = Boolean(
    queue.items.length && queue.items.every((candidate) => bulkSelection[candidate.id])
  );

  function currentCriteria(): ReviewFilterCriteria {
    return {
      status: status || null,
      evidence_tier: evidenceTier.trim() || null,
      event_type: eventType.trim() || null,
      query: query || null,
      max_abs_days: maxDays ? Number(maxDays) : null,
      min_internal_rank: minRank ? Number(minRank) : null,
      has_reviews: reviewHistory ? reviewHistory === "true" : null,
      sort,
      page_size: pageSize,
    };
  }

  function applyCriteria(criteria: ReviewFilterCriteria) {
    setStatus(criteria.status || "");
    setEvidenceTier(criteria.evidence_tier || "");
    setEventType(criteria.event_type || "");
    setQueryInput(criteria.query || "");
    setQuery(criteria.query || "");
    setMaxDays(criteria.max_abs_days == null ? "" : String(criteria.max_abs_days));
    setMinRank(criteria.min_internal_rank == null ? "" : String(criteria.min_internal_rank));
    setReviewHistory(criteria.has_reviews == null ? "" : String(criteria.has_reviews));
    setSort(criteria.sort || "priority");
    setPageSize(criteria.page_size || 25);
    setPage(1);
  }

  async function loadWorkspace() {
    if (!reviewer.trim()) return;
    try {
      const owner = encodeURIComponent(reviewer.trim());
      const [filters, history] = await Promise.all([
        fetchRelationshipAPI<ReviewSavedFilter[]>(`/review/saved-filters?owner=${owner}`),
        fetchRelationshipAPI<ReviewSessionSummary[]>(`/review/sessions?reviewer=${owner}`),
      ]);
      setSavedFilters(filters);
      setSessions(history);
      setActiveSession(history.find((session) => session.status === "active") || null);
      setMessageIsError(false);
      setMessage(`Loaded ${filters.length} saved filter${filters.length === 1 ? "" : "s"} and ${history.length} review session${history.length === 1 ? "" : "s"}.`);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Reviewer workspace failed to load.");
    }
  }

  async function saveCurrentFilter() {
    if (!reviewer.trim() || !filterName.trim()) return;
    try {
      const saved = await fetchRelationshipAPI<ReviewSavedFilter>("/review/saved-filters", {
        method: "POST",
        body: JSON.stringify({ owner: reviewer, name: filterName, criteria: currentCriteria() }),
      });
      setSavedFilters((current) => [...current, saved].sort((a, b) => a.name.localeCompare(b.name)));
      setFilterName("");
      setMessageIsError(false);
      setMessage(`Saved filter ${saved.name}.`);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Saved filter failed.");
    }
  }

  async function startSession() {
    if (!reviewer.trim()) return;
    try {
      const session = await fetchRelationshipAPI<ReviewSessionSummary>("/review/sessions", {
        method: "POST",
        body: JSON.stringify({ reviewer, filter_snapshot: currentCriteria() }),
      });
      setActiveSession(session);
      setSessions((current) => [session, ...current]);
      setMessageIsError(false);
      setMessage("Review session started; subsequent decisions will be included in its summary.");
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Review session failed to start.");
    }
  }

  async function completeSession() {
    if (!activeSession || !reviewer.trim()) return;
    try {
      const session = await fetchRelationshipAPI<ReviewSessionSummary>(`/review/sessions/${activeSession.id}/complete`, {
        method: "POST",
        body: JSON.stringify({ reviewer }),
      });
      setSessions((current) => current.map((row) => row.id === session.id ? session : row));
      setActiveSession(null);
      setMessageIsError(false);
      setMessage(`Session completed with ${session.decision_count} attributed decision${session.decision_count === 1 ? "" : "s"}.`);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Review session failed to complete.");
    }
  }

  async function assignSelected() {
    if (!selected || !reviewer.trim()) return;
    try {
      const row = await fetchRelationshipAPI<ReviewAssignment>("/review/assignments", {
        method: "POST",
        body: JSON.stringify({ candidate_id: selected.id, action: "assign", assignee: reviewer, actor: reviewer, note: "Assigned from reviewer workspace" }),
      });
      setAssignment(row);
      setMessageIsError(false);
      setMessage(`Assigned the selected candidate to ${row.assignee}.`);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Assignment failed.");
    }
  }

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
            expected_revision: selected.review_revision,
            review_session_id: activeSession?.id || null,
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

  async function submitBulkDecision() {
    if (!canSubmitBulk) return;
    setSaving(true);
    setMessage("");
    try {
      const response = await fetchRelationshipAPI<RelationshipBulkReviewResponse>(
        "/review/relationship-candidates/bulk-decisions",
        {
          method: "POST",
          body: JSON.stringify({
            decision,
            reviewer,
            evidence_note: evidenceNote,
            targets: bulkTargets,
            review_session_id: activeSession?.id || null,
          }),
        }
      );
      setEvidenceNote("");
      setBulkSelection({});
      setMessageIsError(false);
      setMessage(`${response.updated_count} candidates updated to ${formatEnum(response.items[0].review_status)}.`);
      setReloadToken((current) => current + 1);
    } catch (error) {
      setMessageIsError(true);
      setMessage(error instanceof Error ? error.message : "Bulk decision failed.");
      setReloadToken((current) => current + 1);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <ReviewerTelemetryStrip />
      <section className="mb-6 border-y border-gray-200 py-4" aria-label="Reviewer workspace">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-52 flex-1 text-sm">
            <span className="text-xs font-medium text-gray-600">Reviewer identity</span>
            <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} maxLength={200} placeholder="Reviewer name" className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <button type="button" onClick={() => void loadWorkspace()} disabled={!reviewer.trim()} className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 disabled:text-gray-400">Load workspace</button>
          {activeSession ? (
            <button type="button" onClick={() => void completeSession()} className="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white">Complete session</button>
          ) : (
            <button type="button" onClick={() => void startSession()} disabled={!reviewer.trim()} className="rounded-md bg-civic-700 px-3 py-2 text-sm font-medium text-white disabled:bg-gray-300">Start session</button>
          )}
          <button type="button" onClick={() => void assignSelected()} disabled={!selected || !reviewer.trim()} className="rounded-md border border-civic-300 px-3 py-2 text-sm font-medium text-civic-700 disabled:border-gray-200 disabled:text-gray-400">Assign selected</button>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="min-w-48 flex-1 text-sm">
            <span className="text-xs font-medium text-gray-600">Save current queue filters</span>
            <input value={filterName} onChange={(event) => setFilterName(event.target.value)} maxLength={120} placeholder="Filter name" className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
          </label>
          <button type="button" onClick={() => void saveCurrentFilter()} disabled={!reviewer.trim() || !filterName.trim()} className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 disabled:text-gray-400">Save filter</button>
          <label className="min-w-52 text-sm">
            <span className="text-xs font-medium text-gray-600">Saved filters</span>
            <select defaultValue="" onChange={(event) => { const saved = savedFilters.find((row) => row.id === event.target.value); if (saved) applyCriteria(saved.criteria); }} className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm">
              <option value="">Choose saved filter</option>
              {savedFilters.map((saved) => <option key={saved.id} value={saved.id}>{saved.name}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500">
          <span>{activeSession ? `Active session started ${formatTimestamp(activeSession.started_at)}` : "No active review session"}</span>
          <span>{sessions.length ? `${sessions.length} recorded session${sessions.length === 1 ? "" : "s"}` : "No session history loaded"}</span>
          {assignment ? <span>Selected assignment: {formatEnum(assignment.action)} to {assignment.assignee}</span> : null}
        </div>
      </section>
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
          <div className="flex flex-wrap items-end justify-between gap-3 sm:col-span-2 xl:col-span-4">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <p className="tabular-nums text-gray-500">
                {queue.total} {queue.total === 1 ? "candidate" : "candidates"}
              </p>
              {queue.items.length ? (
                <button
                  type="button"
                  onClick={() => {
                    if (allPageSelected) {
                      setBulkSelection((current) => {
                        const next = { ...current };
                        queue.items.forEach((candidate) => delete next[candidate.id]);
                        return next;
                      });
                    } else {
                      setBulkSelection((current) => {
                        const next = { ...current };
                        queue.items.forEach((candidate) => {
                          next[candidate.id] = {
                            candidate_id: candidate.id,
                            expected_status: candidate.review_status,
                            expected_revision: candidate.review_revision,
                          };
                        });
                        return next;
                      });
                    }
                  }}
                  className="font-medium text-civic-700 hover:underline"
                >
                  {allPageSelected ? "Deselect page" : "Select page"}
                </button>
              ) : null}
              {bulkTargets.length ? (
                <button
                  type="button"
                  onClick={() => setBulkSelection({})}
                  className="font-medium text-civic-700 hover:underline"
                >
                  Clear {bulkTargets.length} selected
                </button>
              ) : null}
            </div>
            <div className="flex items-center gap-4">
              <a
                href={`${API_BASE}/review/relationship-audit-history/export`}
                download
                className="text-sm font-medium text-civic-700 hover:underline"
              >
                Export audit history
              </a>
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
              <div
                key={candidate.id}
                className={`grid grid-cols-[2rem_minmax(0,1fr)] rounded-lg border bg-white transition-colors ${
                  isSelected
                    ? "border-civic-500 ring-1 ring-civic-200"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <label className="flex items-start justify-center px-2 py-5">
                  <input
                    type="checkbox"
                    checked={Boolean(bulkSelection[candidate.id])}
                    onChange={(event) => {
                      setBulkSelection((current) => {
                        const next = { ...current };
                        if (event.target.checked) {
                          next[candidate.id] = {
                            candidate_id: candidate.id,
                            expected_status: candidate.review_status,
                            expected_revision: candidate.review_revision,
                          };
                        } else {
                          delete next[candidate.id];
                        }
                        return next;
                      });
                    }}
                    aria-label={`Select ${candidate.person_name} relationship candidate`}
                    className="h-4 w-4 rounded border-gray-300 text-civic-700"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(candidate.id);
                    setMessage("");
                    setEvidenceNote("");
                  }}
                  className="min-w-0 p-4 pl-2 text-left"
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
              </div>
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
                {bulkTargets.length ? (
                  <button
                    type="button"
                    onClick={submitBulkDecision}
                    disabled={!canSubmitBulk}
                    className="w-full rounded-md border border-civic-700 bg-white px-4 py-2 text-sm font-medium text-civic-800 disabled:cursor-not-allowed disabled:border-gray-300 disabled:text-gray-400"
                  >
                    {saving ? "Recording..." : `Record for ${bulkTargets.length} selected`}
                  </button>
                ) : null}
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
    </>
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
