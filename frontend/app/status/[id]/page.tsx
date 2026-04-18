'use client';

import { Suspense, useEffect, useState, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getAnalysis, getReportUrl } from '@/lib/api';
import type { AnalysisResponse } from '@/lib/api';
import AgentStatusRow from '@/components/AgentStatusRow';
import ScoreGauge from '@/components/ScoreGauge';

function StatusContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const id = params.id as string;
  const paymentSuccess = searchParams.get('payment') === 'success';

  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState('');
  const [polling, setPolling] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const result = await getAnalysis(id);
      setData(result);
      if (result.status === 'complete' || result.status === 'failed') {
        setPolling(false);
      }
    } catch {
      setError('Could not load analysis status.');
    }
  }, [id]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [polling, fetchStatus]);

  const completedCount =
    data?.agents.filter((a) => a.status === 'complete').length || 0;
  const totalAgents = data?.agents.length || 7;
  const progressPct = Math.round((completedCount / totalAgents) * 100);
  const isComplete = data?.status === 'complete';
  const isFailed = data?.status === 'failed';

  return (
    <>
      {paymentSuccess && (
        <div className="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg mb-6 text-sm font-medium">
          Payment confirmed &mdash; analysis starting!
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900 mb-1">
              Analysis Status
            </h1>
            <p className="text-gray-500 text-sm">
              {data.address_formatted || data.address_input}
            </p>
            <div className="mt-3">
              {isComplete ? (
                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-green-100 text-green-800">
                  Complete
                </span>
              ) : isFailed ? (
                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800">
                  Failed
                </span>
              ) : (
                <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 animate-pulse-blue">
                  Processing
                </span>
              )}
            </div>
          </div>

          <div className="mb-8">
            <div className="flex justify-between text-sm text-gray-500 mb-1">
              <span>
                {completedCount} / {totalAgents} agents complete
              </span>
              <span>{progressPct}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {isComplete && data.overall_score !== null && (
            <div className="bg-white rounded-2xl border border-gray-200 p-8 mb-8 text-center animate-score-reveal">
              <div className="relative inline-flex">
                <ScoreGauge score={data.overall_score} size={180} />
              </div>
              <p className="mt-4 text-gray-500 text-sm">
                Overall Readiness Score
              </p>
            </div>
          )}

          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden mb-8">
            {data.agents.map((agent) => (
              <AgentStatusRow key={agent.agent_name} agent={agent} />
            ))}
          </div>

          {isComplete && (
            <div className="flex flex-col sm:flex-row gap-3">
              <a
                href={getReportUrl(id)}
                className="flex-1 text-center bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-colors"
              >
                Download PDF Report
              </a>
              <Link
                href={`/report/${id}`}
                className="flex-1 text-center border-2 border-gray-300 hover:border-blue-600 text-gray-700 hover:text-blue-600 font-bold py-3 rounded-xl transition-colors"
              >
                View Report Page
              </Link>
            </div>
          )}
        </>
      )}

      {!data && !error && (
        <div className="text-center py-20 text-gray-400">
          Loading analysis status...
        </div>
      )}
    </>
  );
}

export default function StatusPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto px-6 py-12">
        <Suspense
          fallback={
            <div className="text-center py-20 text-gray-400">Loading...</div>
          }
        >
          <StatusContent />
        </Suspense>
      </div>
    </main>
  );
}
