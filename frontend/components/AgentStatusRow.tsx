'use client';

import type { Agent } from '@/lib/api';

const AGENT_ICONS: Record<string, string> = {
  airspace: '✈️',
  zoning: '🏗️',
  power: '⚡',
  structural: '🏢',
  regulatory: '📋',
  cost: '💰',
  noise: '🌿',
};

const AGENT_LABELS: Record<string, string> = {
  airspace: 'FAA Airspace Analysis',
  zoning: 'Zoning & Land Use',
  power: 'Power Infrastructure',
  structural: 'Structural Assessment',
  regulatory: 'Regulatory Landscape',
  cost: 'Cost Model',
  noise: 'Environmental & Noise',
};

function getStatusPill(status: string) {
  switch (status) {
    case 'complete':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
          Complete
        </span>
      );
    case 'running':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 animate-pulse-blue">
          Running
        </span>
      );
    case 'failed':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
          Failed
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
          Pending
        </span>
      );
  }
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-500';
  if (score >= 60) return 'text-yellow-500';
  if (score >= 40) return 'text-orange-500';
  return 'text-red-500';
}

export default function AgentStatusRow({ agent }: { agent: Agent }) {
  const icon = AGENT_ICONS[agent.agent_name] || '📌';
  const label = AGENT_LABELS[agent.agent_name] || agent.agent_name;

  return (
    <div className="flex items-center justify-between py-4 px-4 border-b border-gray-100 last:border-0 hover:bg-gray-50 transition-colors">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <span className="text-xl flex-shrink-0">{icon}</span>
        <div className="min-w-0">
          <div className="font-semibold text-gray-900 text-sm">{label}</div>
          {agent.status === 'complete' && agent.summary && (
            <div className="text-xs text-gray-500 truncate max-w-md">
              {agent.summary}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-4 flex-shrink-0">
        {getStatusPill(agent.status)}
        {agent.status === 'complete' && agent.score !== null && (
          <span
            className={`text-lg font-bold tabular-nums ${getScoreColor(agent.score)}`}
          >
            {agent.score}
          </span>
        )}
      </div>
    </div>
  );
}
