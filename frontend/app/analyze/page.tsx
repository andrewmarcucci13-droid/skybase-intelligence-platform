'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { createAnalysis } from '@/lib/api';

function AnalyzeForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const cancelled = searchParams.get('cancelled');

  const [address, setAddress] = useState('');
  const [email, setEmail] = useState('');
  const [propertyType, setPropertyType] = useState('unknown');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await createAnalysis(address, email, propertyType);

      if (result.checkout_url) {
        window.location.href = result.checkout_url;
      } else {
        router.push(`/status/${result.analysis_id}?pending_payment=true`);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Something went wrong';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {cancelled && (
        <div className="bg-yellow-50 border border-yellow-200 text-yellow-800 px-4 py-3 rounded-lg mb-6 text-sm">
          Payment was cancelled. You can try again below.
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm">
          {error}
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 space-y-6"
      >
        <div>
          <label
            htmlFor="address"
            className="block text-sm font-semibold text-gray-700 mb-1"
          >
            Property Address *
          </label>
          <input
            id="address"
            type="text"
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="e.g., 1600 Pennsylvania Ave NW, Washington, DC 20500"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg text-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          />
          <p className="mt-1 text-xs text-gray-400">
            US addresses only. Include city, state, and ZIP.
          </p>
        </div>

        <div>
          <label
            htmlFor="email"
            className="block text-sm font-semibold text-gray-700 mb-1"
          >
            Email Address *
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
          />
          <p className="mt-1 text-xs text-gray-400">
            For report delivery and Stripe receipt.
          </p>
        </div>

        <div>
          <label
            htmlFor="propertyType"
            className="block text-sm font-semibold text-gray-700 mb-1"
          >
            Property Type{' '}
            <span className="font-normal text-gray-400">(optional)</span>
          </label>
          <select
            id="propertyType"
            value={propertyType}
            onChange={(e) => setPropertyType(e.target.value)}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-white"
          >
            <option value="unknown">Select type...</option>
            <option value="rooftop">Commercial Rooftop</option>
            <option value="ground">Ground Level</option>
            <option value="airport">Airport-Adjacent</option>
            <option value="garage">Parking Garage</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-bold py-4 rounded-xl text-lg transition-colors"
        >
          {loading ? 'Creating analysis...' : 'Continue to Payment — $499'}
        </button>

        <p className="text-xs text-gray-400 text-center">
          Secure payment via Stripe. You&apos;ll be redirected to complete
          checkout.
        </p>
      </form>
    </>
  );
}

export default function AnalyzePage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-gray-900 mb-3">
            Analyze Your Site
          </h1>
          <p className="text-gray-500">
            Enter your property address for a comprehensive vertiport
            feasibility analysis.
          </p>
        </div>
        <Suspense fallback={<div className="text-center text-gray-400">Loading...</div>}>
          <AnalyzeForm />
        </Suspense>
      </div>
    </main>
  );
}
