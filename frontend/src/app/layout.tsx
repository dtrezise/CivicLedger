import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "CivicLedger",
  description: "Federal public financial disclosure tracker",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav className="bg-white border-b border-gray-200 sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-14 items-center">
              <Link href="/" className="text-xl font-bold text-civic-700">
                CivicLedger
              </Link>
              <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-sm">
                <Link
                  href="/browse"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Browse
                </Link>
                <Link
                  href="/methodology"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Methodology
                </Link>
                <Link
                  href="/sources"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Sources
                </Link>
                <Link
                  href="/review"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Review
                </Link>
                <Link
                  href="/evidence"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Evidence
                </Link>
                <Link
                  href="/quality"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Quality
                </Link>
                <Link
                  href="/admin/runs"
                  className="text-gray-600 hover:text-civic-700"
                >
                  Runs
                </Link>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
        <footer className="border-t border-gray-200 mt-12 py-6 text-center text-xs text-gray-400">
          CivicLedger &middot; Federal public financial disclosures &middot;{" "}
          <Link href="/methodology" className="underline">
            Methodology
          </Link>
        </footer>
      </body>
    </html>
  );
}
