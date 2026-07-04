"use client";

import { useState, useEffect, use } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PersonDetail, TradeRow } from "@/lib/types";

export default function TradesPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [assetClassFilter, setAssetClassFilter] = useState("");
  const [sort, setSort] = useState("trade_date");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getPerson(id).then(setPerson).catch(console.error);
  }, [id]);

  useEffect(() => {
    setLoading(true);
    api
      .getPersonTrades(id, {
        type: actionFilter || undefined,
        asset_class: assetClassFilter || undefined,
        sort,
        page,
        page_size: 20,
      })
      .then((data) => {
        setTrades(data.items);
        setTotal(data.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id, actionFilter, assetClassFilter, sort, page]);

  const totalPages = Math.ceil(total / 20);

  const actionColor = (a: string) => {
    if (a === "BUY") return "text-green-700 bg-green-50";
    if (a === "SELL") return "text-red-700 bg-red-50";
    return "text-gray-700 bg-gray-50";
  };

  return (
    <div>
      <div className="mb-4">
        <Link href={`/people/${id}`} className="text-sm text-civic-600 hover:underline">
          &larr; Back to profile
        </Link>
      </div>

      <h1 className="text-2xl font-bold mb-1">{person?.full_name || "..."}</h1>
      <h2 className="text-gray-500 mb-6">Trades ({total})</h2>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={actionFilter}
          onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
          className="border border-gray-300 rounded px-3 py-1.5 text-sm"
        >
          <option value="">All Actions</option>
          <option value="BUY">Buy</option>
          <option value="SELL">Sell</option>
          <option value="EXCHANGE">Exchange</option>
        </select>

        <select
          value={assetClassFilter}
          onChange={(e) => { setAssetClassFilter(e.target.value); setPage(1); }}
          className="border border-gray-300 rounded px-3 py-1.5 text-sm"
        >
          <option value="">All Asset Classes</option>
          <option value="equity">Equity</option>
          <option value="etf">ETF</option>
          <option value="mutual_fund">Mutual Fund</option>
          <option value="bond">Bond</option>
          <option value="crypto">Crypto</option>
        </select>

        <select
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="border border-gray-300 rounded px-3 py-1.5 text-sm"
        >
          <option value="trade_date">Date (asc)</option>
          <option value="-trade_date">Date (desc)</option>
          <option value="-disclosure_lag_days">Lag (desc)</option>
          <option value="disclosure_lag_days">Lag (asc)</option>
        </select>
      </div>

      {loading ? (
        <p className="text-gray-400">Loading...</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                  <th className="py-2 pr-3">Date</th>
                  <th className="py-2 pr-3">Action</th>
                  <th className="py-2 pr-3">Asset</th>
                  <th className="py-2 pr-3">Ticker</th>
                  <th className="py-2 pr-3">Value Range</th>
                  <th className="py-2 pr-3">Lag</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="py-2 pr-3">{t.trade_date}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${actionColor(
                          t.action
                        )}`}
                      >
                        {t.action}
                      </span>
                    </td>
                    <td className="py-2 pr-3 max-w-[200px] truncate">
                      {t.asset_display_name}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">
                      {t.ticker || "—"}
                    </td>
                    <td className="py-2 pr-3 text-xs">{t.value_range_label}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={`text-xs ${
                          t.disclosure_lag_days > 60
                            ? "text-red-600"
                            : t.disclosure_lag_days > 30
                            ? "text-yellow-600"
                            : "text-green-600"
                        }`}
                      >
                        {t.disclosure_lag_days}d
                      </span>
                    </td>
                    <td className="py-2">
                      <Link
                        href={`/trades/${t.id}`}
                        className="text-civic-600 hover:underline text-xs"
                      >
                        Detail →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex justify-center gap-2 mt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border rounded disabled:opacity-30 text-sm"
              >
                Prev
              </button>
              <span className="px-3 py-1 text-sm text-gray-500">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 border rounded disabled:opacity-30 text-sm"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
