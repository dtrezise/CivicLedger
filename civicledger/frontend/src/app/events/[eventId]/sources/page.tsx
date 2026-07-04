"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type EventDetail = {
  id?: string;
  event_id?: string;
  date?: string;
  label?: string;
  title?: string;
  event_type?: string;
  type?: string;
  description?: string;
  sources?: string[];
  source_links?: string[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

function getEventId(e: EventDetail) {
  return e.id ?? e.event_id ?? "";
}

function getEventTitle(e: EventDetail) {
  return e.label ?? e.title ?? "Event";
}

function getEventType(e: EventDetail) {
  return e.event_type ?? e.type ?? "";
}

function getSources(e: EventDetail) {
  return e.sources ?? e.source_links ?? [];
}

export default function EventSourcesPage({
  params,
}: {
  params: { eventId: string };
}) {
  const { eventId } = params;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [event, setEvent] = useState<EventDetail | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      setEvent(null);

      try {
        // Preferred endpoint (we’ll add it if missing):
        // GET /events/{event_id}
        const res = await fetch(`${API_BASE}/events/${eventId}`, {
          cache: "no-store",
        });

        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(`Failed to load event (${res.status}). ${text}`);
        }

        const data = (await res.json()) as EventDetail;

        if (!cancelled) setEvent(data);
      } catch (e: any) {
        if (!cancelled) setError(e?.message ?? "Failed to load event sources.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  const sources = useMemo(() => (event ? getSources(event) : []), [event]);

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Event Sources</h1>
          <p className="mt-1 text-sm text-gray-600">
            A neutral list of source links supporting this event.
          </p>
        </div>
        <Link href="/" className="text-sm underline hover:text-blue-600">
          Home
        </Link>
      </div>

      {loading && <div className="text-sm text-gray-600">Loading…</div>}

      {!loading && error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
          <div className="mt-2 text-xs text-gray-700">
            Event ID: <span className="font-mono">{eventId}</span>
          </div>
          <div className="mt-3">
            <Link href="/browse" className="underline hover:text-blue-600">
              Back to Browse
            </Link>
          </div>
        </div>
      )}

      {!loading && !error && event && (
        <div className="rounded-lg border bg-white p-5">
          <div className="mb-4">
            <div className="text-lg font-semibold">{getEventTitle(event)}</div>
            <div className="mt-1 text-sm text-gray-600">
              <span className="mr-3">
                Date: <span className="font-mono">{event.date ?? "—"}</span>
              </span>
              {getEventType(event) ? (
                <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">
                  {getEventType(event)}
                </span>
              ) : null}
            </div>
            {event.description ? (
              <p className="mt-3 text-sm text-gray-700">{event.description}</p>
            ) : null}
          </div>

          <div className="border-t pt-4">
            <div className="text-sm font-medium">Sources</div>

            {sources.length === 0 ? (
              <div className="mt-2 text-sm text-gray-600">
                No sources listed for this event yet.
              </div>
            ) : (
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">
                {sources.map((url, i) => (
                  <li key={`${url}-${i}`}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline hover:text-blue-600 break-all"
                    >
                      {url}
                    </a>
                  </li>
                ))}
              </ol>
            )}

            <div className="mt-6 text-xs text-gray-600">
              Note: Sources are provided for transparency and may include primary records or reputable reporting.
            </div>
          </div>

          <div className="mt-5 text-xs text-gray-500">
            Event ID: <span className="font-mono">{getEventId(event) || eventId}</span>
          </div>
        </div>
      )}
    </main>
  );
}
