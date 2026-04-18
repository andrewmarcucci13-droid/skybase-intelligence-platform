import Link from 'next/link';

const features = [
  { title: 'FAA Airspace Class & Waivers', icon: '✈️' },
  { title: 'Zoning & Land Use', icon: '🏗️' },
  { title: 'Power Infrastructure', icon: '⚡' },
  { title: 'Structural Assessment', icon: '🏢' },
  { title: 'Regulatory Landscape (5 States)', icon: '📋' },
  { title: 'Full Cost Model (CapEx + ROI)', icon: '💰' },
  { title: 'Environmental & Noise', icon: '🌿' },
  { title: '30-Page PDF Report', icon: '📄' },
];

const steps = [
  {
    num: '1',
    title: 'Enter Your Address',
    desc: 'Provide your property address for analysis',
  },
  {
    num: '2',
    title: '7 AI Agents Analyze',
    desc: 'FAA airspace, zoning, power, structure, regulations, cost, environment',
  },
  {
    num: '3',
    title: 'Download Your Report',
    desc: 'Get your comprehensive PDF Vertiport Readiness Report',
  },
];

export default function LandingPage() {
  return (
    <main>
      {/* Hero */}
      <section className="bg-gradient-to-br from-[#0a1628] via-[#1e3a5f] to-blue-600 text-white">
        <div className="max-w-5xl mx-auto px-6 py-24 text-center">
          <h1 className="text-4xl sm:text-5xl font-extrabold leading-tight mb-6">
            Know If Your Site Can Host an eVTOL Vertiport&nbsp;&mdash; In 30
            Minutes
          </h1>
          <p className="text-lg sm:text-xl text-blue-200 max-w-3xl mx-auto mb-10">
            AI-powered feasibility analysis replacing $50K&ndash;$150K
            engineering studies. 7 intelligence agents. One comprehensive report.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/analyze"
              className="inline-flex items-center justify-center bg-blue-600 hover:bg-blue-700 text-white text-lg font-bold px-8 py-4 rounded-xl transition-colors"
            >
              Analyze My Site &mdash; $499
            </Link>
            <Link
              href="#features"
              className="inline-flex items-center justify-center border-2 border-white/30 hover:border-white/60 text-white text-lg font-semibold px-8 py-4 rounded-xl transition-colors"
            >
              See Sample Report
            </Link>
          </div>
        </div>
      </section>

      {/* Social proof bar */}
      <section className="bg-[#0a1628] border-t border-white/10">
        <div className="max-w-5xl mx-auto px-6 py-5 flex flex-wrap justify-center gap-8 text-sm text-blue-300 font-medium">
          <span>7 Intelligence Agents</span>
          <span className="text-white/20">|</span>
          <span>30-Min Analysis</span>
          <span className="text-white/20">|</span>
          <span>FAA-Compliant</span>
          <span className="text-white/20">|</span>
          <span>Instant PDF Report</span>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-20 bg-white">
        <div className="max-w-5xl mx-auto px-6">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-14">
            How It Works
          </h2>
          <div className="grid md:grid-cols-3 gap-10">
            {steps.map((s) => (
              <div key={s.num} className="text-center">
                <div className="w-14 h-14 rounded-full bg-blue-600 text-white text-2xl font-bold flex items-center justify-center mx-auto mb-5">
                  {s.num}
                </div>
                <h3 className="text-lg font-bold text-gray-900 mb-2">
                  {s.title}
                </h3>
                <p className="text-gray-500">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* What's Included */}
      <section id="features" className="py-20 bg-gray-50">
        <div className="max-w-5xl mx-auto px-6">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-14">
            What&apos;s Included
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {features.map((f) => (
              <div
                key={f.title}
                className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow"
              >
                <span className="text-2xl mb-3 block">{f.icon}</span>
                <span className="font-semibold text-gray-900 text-sm">
                  {f.title}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section className="py-20 bg-white">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-14">
            Pricing
          </h2>
          <div className="grid md:grid-cols-2 gap-8">
            {/* Single */}
            <div className="rounded-2xl border-2 border-blue-600 p-8 relative">
              <div className="absolute -top-3 left-6 bg-blue-600 text-white text-xs font-bold px-3 py-1 rounded-full">
                MOST POPULAR
              </div>
              <h3 className="text-2xl font-bold text-gray-900 mb-2">
                Single Analysis
              </h3>
              <div className="text-4xl font-extrabold text-gray-900 mb-4">
                $499
              </div>
              <ul className="space-y-2 text-gray-600 text-sm mb-8">
                <li>All 7 intelligence agents</li>
                <li>Comprehensive PDF report</li>
                <li>FAA airspace + zoning analysis</li>
                <li>Cost model with ROI projections</li>
                <li>Environmental & noise assessment</li>
                <li>Regulatory landscape review</li>
              </ul>
              <Link
                href="/analyze"
                className="block text-center bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg transition-colors"
              >
                Get Your Report
              </Link>
            </div>
            {/* Subscription */}
            <div className="rounded-2xl border border-gray-200 p-8">
              <h3 className="text-2xl font-bold text-gray-900 mb-2">
                Regulatory Monitor
              </h3>
              <div className="text-4xl font-extrabold text-gray-900 mb-1">
                $99
                <span className="text-lg font-normal text-gray-500">
                  /month
                </span>
              </div>
              <p className="text-sm text-gray-500 mb-4">
                Continuous monitoring
              </p>
              <ul className="space-y-2 text-gray-600 text-sm mb-8">
                <li>Real-time regulatory updates</li>
                <li>FAA rule change alerts</li>
                <li>State legislation tracking</li>
                <li>Monthly summary reports</li>
                <li>Email notifications</li>
              </ul>
              <Link
                href="/analyze"
                className="block text-center border-2 border-gray-300 hover:border-blue-600 text-gray-700 hover:text-blue-600 font-bold py-3 rounded-lg transition-colors"
              >
                Subscribe
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#0a1628] text-gray-400 text-center py-8 text-sm">
        SkyBase Intelligence Platform &copy; {new Date().getFullYear()}
      </footer>
    </main>
  );
}
