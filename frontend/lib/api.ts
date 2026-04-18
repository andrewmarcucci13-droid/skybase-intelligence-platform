const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Agent {
  agent_name: string;
  status: string;
  score: number | null;
  summary: string | null;
  warnings: string[];
}

export interface AnalysisResponse {
  analysis_id: string;
  status: string;
  overall_score: number | null;
  address_formatted: string | null;
  address_input: string;
  report_url: string | null;
  created_at: string | null;
  completed_at: string | null;
  agents: Agent[];
}

export interface CreateAnalysisResponse {
  analysis_id: string;
  checkout_url: string;
}

export interface CheckoutResponse {
  checkout_url: string;
}

export async function createAnalysis(
  address: string,
  email: string,
  propertyType?: string
): Promise<CreateAnalysisResponse> {
  const res = await fetch(`${API_URL}/api/v1/analyses/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      address,
      customer_email: email,
      property_type: propertyType || 'unknown',
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || 'Failed to create analysis');
  }
  return res.json();
}

export async function getAnalysis(id: string): Promise<AnalysisResponse> {
  const res = await fetch(`${API_URL}/api/v1/analyses/${id}`);
  if (!res.ok) {
    throw new Error('Analysis not found');
  }
  return res.json();
}

export async function createCheckoutSession(
  analysisId: string
): Promise<CheckoutResponse> {
  const res = await fetch(`${API_URL}/api/v1/analyses/${analysisId}/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Checkout failed' }));
    throw new Error(err.detail || 'Failed to create checkout session');
  }
  return res.json();
}

export function getReportUrl(analysisId: string): string {
  return `${API_URL}/api/v1/analyses/${analysisId}/report`;
}
