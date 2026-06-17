import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Redmine GraphRAG — AI-Powered Issue Intelligence',
  description:
    'Chat-based AI question answering over 44,000 Redmine issues, 41,427 journal discussions, ' +
    'and 10,253 attachments spanning 20 years of Redmine development history. ' +
    'Upload images for OCR analysis. Powered by vector + graph fusion.',
  keywords: ['Redmine', 'RAG', 'GraphRAG', 'issue tracker', 'AI', 'search', 'chat', 'OCR'],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <div className="bg-animated" aria-hidden="true" />
        <div className="bg-animated-extra" aria-hidden="true" />
        <div className="app-layout">
          {children}
        </div>
      </body>
    </html>
  );
}
