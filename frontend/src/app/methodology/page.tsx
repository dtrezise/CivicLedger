"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type { MethodologyResponse } from "@/lib/types";

export default function MethodologyPage() {
  const [data, setData] = useState<MethodologyResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getMethodology()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-400">Loading...</p>;
  if (!data) return <p className="text-red-500">Failed to load methodology.</p>;

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
    </div>
  );
}
