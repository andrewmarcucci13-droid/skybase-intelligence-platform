'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getAnalysis, getReportUrl } from '@/lib/api';
import type { AnalysisResponse } from '@/lib/api';
import ScoreGauge from '@/components/ScoreGauge';

const STRIPE_SUB_PRICE_ID = 'price_1TNhCiB6nlyxBcZvchN2Q9CA';

export default function ReportPage() {
  const params = useParams();
  const id = params.id as string;

  const [data, setData] = useState<AnalysisResponse | null>(null);

  useEffect(() => {
    getAnalysis(id).then(setData).catch(() => {});
  }, [id]);

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-6 py-12">
        {data ? (
          <>
            <div className="text-center mb-10">
              <h1 className="text-2xl font-bold text-gray-900 mb-2">
                Your Vertiport Readiness Report
              </h1>
              <p className="text-gray-500">
                {data.address_formatted || data.address_input}
              </p>
            </div>

            {data.overall_score !== null && (
              <div className="bg-white rounded-2xl border border-gray-200 p-8 mb-8 text-center">
                <div className="relative inline-flex">
                  <ScoreGauge score={data.overall_score} size={180} />
                </div>
                <p className="mt-4 text-gray-500 text-sm">
                  Overall Readiness Score
                </p>
              </div>
            )}

            {/* Download */}
            <div className="bg-white rounded-2xl border border-gray-200 p-8 mb-8 text-center">
              <h2 className="text-lg font-bold text-gray-900 mb-4">
                Download Your Report
              </h2>
              <a
                href={getReportUrl(id)}
                className="inline-flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white font-bold px-8 py-4 rounded-xl text-lg transition-colors"
              >
                Download PDF Report
              </a>
              <p className="mt-3 text-xs text-gray-400">
                Your comprehensive Vertiport Readiness Report as a
                professional PDF.
              </p>
            </div>

            {/* Subscription upsell */}
            <div className="bg-gradient-to-br from-[#0a1628] to-[#1e3a5f] rounded-2xl p-8 text-center text-white mb-8">
              <h2 className="text-xl font-bold mb-2">
                Stay Ahead of Regulatory Changes
              </h2>
              <p className="text-blue-300 mb-6 text-sm">
                SkyBase Regulatory Monitor tracks FAA rules, state legislation,
                and local zoning changes that affect your site — $99/month.
              </p>
              <a
                href={`https://buy.stripe.com/${STRIPE_SUB_PRICE_ID}`}
                className="inline-flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white font-bold px-8 py-3 rounded-xl transition-colors"
              >
                Subscribe — $99/month
              </a>
            </div>

            <div className="text-center">
              <Link
                href="/analyze"
                className="text-blue-600 hover:text-blue-700 font-semibold text-sm"
              >
                Run Another Analysis
              </Link>
            </div>
          </>
        ) : (
          <div className="text-center py-20 text-gray-400">
            Loading report...
          </div>
        )}
      </div>
    </main>
  );
}
