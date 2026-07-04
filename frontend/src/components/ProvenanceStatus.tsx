import type { ReactNode } from "react";
import type { MetaStatus } from "@/lib/types";

type StatusLike = Partial<MetaStatus> | null | undefined;

export type MetadataItem = {
  label: string;
  value: ReactNode;
  missingLabel?: string;
};

function hasDisplayValue(value: ReactNode) {
  return value !== null && value !== undefined && value !== "";
}

export function formatDateTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function isFixtureStatus(status: StatusLike) {
  if (!status) return false;
  const dataset = String(status?.dataset_version ?? "").toLowerCase();
  const ingestionKnownMissing =
    "last_ingestion_run_at" in status && !status.last_ingestion_run_at;

  return (
    ingestionKnownMissing ||
    ["seed", "fixture", "demo", "sample", "mock"].some((token) =>
      dataset.includes(token)
    )
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "fixture" | "complete" | "attention";
}) {
  const toneClass =
    tone === "fixture"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : tone === "complete"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : tone === "attention"
      ? "border-yellow-200 bg-yellow-50 text-yellow-800"
      : "border-gray-200 bg-gray-50 text-gray-700";

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${toneClass}`}
    >
      {children}
    </span>
  );
}

export function DemoFixtureBanner({
  status,
  className = "",
}: {
  status: StatusLike;
  className?: string;
}) {
  if (!isFixtureStatus(status)) return null;

  return (
    <div
      className={`rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 ${className}`}
    >
      <div className="font-medium">Demo fixture data</div>
      <div className="mt-1 text-xs leading-relaxed text-amber-800">
        This view is using seeded or demo-labeled data. Treat values as a
        product fixture unless a completed ingestion timestamp is shown.
      </div>
    </div>
  );
}

export function MetadataSummary({
  title = "Data Status",
  description,
  status,
  items,
  children,
  className = "",
}: {
  title?: string;
  description?: ReactNode;
  status?: StatusLike;
  items: MetadataItem[];
  children?: ReactNode;
  className?: string;
}) {
  const fixture = isFixtureStatus(status);

  return (
    <section
      className={`rounded-lg border border-gray-200 bg-white p-4 shadow-sm ${className}`}
      aria-label={title}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
          {description ? (
            <p className="mt-1 text-xs leading-relaxed text-gray-500">
              {description}
            </p>
          ) : null}
        </div>
        {status ? (
          <StatusBadge tone={fixture ? "fixture" : "complete"}>
            {fixture ? "Demo / fixture" : "Ingested data"}
          </StatusBadge>
        ) : (
          <StatusBadge>Metadata unavailable</StatusBadge>
        )}
      </div>

      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((item) => (
          <div key={item.label}>
            <dt className="text-xs text-gray-500">{item.label}</dt>
            <dd className="mt-1 break-words text-sm text-gray-800">
              {hasDisplayValue(item.value) ? (
                item.value
              ) : (
                <span className="text-gray-400">
                  {item.missingLabel ?? "Not provided"}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>

      {children ? <div className="mt-4">{children}</div> : null}
    </section>
  );
}
