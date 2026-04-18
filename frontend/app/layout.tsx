import type { Metadata } from 'next';
import './globals.css';
import NavBar from '@/components/NavBar';

export const metadata: Metadata = {
  title: 'SkyBase Intelligence Platform — Vertiport Feasibility Analysis',
  description:
    'AI-powered vertiport site feasibility analysis. 7 intelligence agents, one comprehensive report.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <NavBar />
        {children}
      </body>
    </html>
  );
}
