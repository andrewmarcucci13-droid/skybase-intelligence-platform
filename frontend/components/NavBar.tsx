'use client';

import Link from 'next/link';

export default function NavBar() {
  return (
    <nav className="bg-[#0a1628] border-b border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-white font-extrabold text-xl tracking-wider">
              SKYBASE
            </span>
            <span className="text-blue-400 text-xs tracking-widest uppercase hidden sm:inline">
              Intelligence
            </span>
          </Link>
          <Link
            href="/analyze"
            className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-lg text-sm font-semibold transition-colors"
          >
            Analyze Site
          </Link>
        </div>
      </div>
    </nav>
  );
}
