'use client';

import { useState, useCallback } from 'react';
import QueryInput from '@/components/QueryInput';
import AnswerStream from '@/components/AnswerStream';
import MetadataBadges from '@/components/MetadataBadges';
import RelatedIssues from '@/components/RelatedIssues';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Stage = 'idle' | 'parsing' | 'retrieving' | 'compressing' | 'synthesizing' | 'done';

interface ParsedQuery {
  intent?: string;
  complexity?: string;
  needs_graph?: boolean;
  needs_attachments?: boolean;
  entities?: { issue_ids?: number[] };
}

interface FusedIssue {
  issue_id: number;
  subject: string;
  status?: string;
  tracker?: string;
  rrf_score?: number;
}

export default function HomePage() {
  const [query, setQuery]           = useState('');
  const [answer, setAnswer]         = useState('');
  const [parsed, setParsed]         = useState<ParsedQuery | null>(null);
  const [fusedIssues, setFusedIssues] = useState<FusedIssue[]>([]);
  const [fusedCount, setFusedCount] = useState(0);
  const [elapsedMs, setElapsedMs]   = useState(0);
  const [stage, setStage]           = useState<Stage>('idle');
  const [isLoading, setIsLoading]   = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError]           = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!query.trim() || isLoading) return;

    // Reset state
    setAnswer('');
    setParsed(null);
    setFusedIssues([]);
    setFusedCount(0);
    setElapsedMs(0);
    setError(null);
    setIsLoading(true);
    setIsStreaming(false);
    setIsThinking(false);
    setStage('parsing');

    const t0 = Date.now();

    try {
      // Use SSE streaming endpoint
      const url = `${API_URL}/ask/stream?query=${encodeURIComponent(query)}`;
      const evtSource = new EventSource(url);

      evtSource.addEventListener('parsed', e => {
        try {
          const data = JSON.parse(e.data);
          setParsed(data);
          setStage('retrieving');
        } catch {}
      });

      evtSource.addEventListener('retrieved', e => {
        try {
          const data = JSON.parse(e.data);
          setFusedCount(data.fused_count || 0);
          setStage('synthesizing');
          setIsStreaming(true);
          setIsThinking(true);
        } catch {}
        setStage('synthesizing');
      });

      evtSource.addEventListener('context_ready', () => {
        setStage('synthesizing');
        setIsStreaming(true);
      });

      evtSource.addEventListener('token', e => {
        setIsThinking(false);
        setAnswer(prev => prev + e.data);
      });

      evtSource.addEventListener('done', () => {
        evtSource.close();
        setStage('done');
        setIsStreaming(false);
        setIsLoading(false);
        setElapsedMs(Date.now() - t0);
      });

      evtSource.onerror = async () => {
        evtSource.close();
        // Fallback to non-streaming POST /ask
        try {
          setStage('synthesizing');
          const resp = await fetch(`${API_URL}/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query }),
          });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          setAnswer(data.answer || '');
          setParsed(data.parsed || null);
          setFusedCount(data.fused_count || 0);
          setElapsedMs(data.elapsed_ms || (Date.now() - t0));
          if (data.error) setError(data.error);
        } catch (err: any) {
          setError(err.message || 'Request failed');
        } finally {
          setStage('done');
          setIsStreaming(false);
          setIsLoading(false);
        }
      };

    } catch (err: any) {
      setError(err.message || 'Request failed');
      setStage('idle');
      setIsLoading(false);
    }
  }, [query, isLoading]);

  const hasResult = stage !== 'idle' || answer || error;

  return (
    <main className="main-container" id="main-content">
      {/* Header */}
      <header className="header">
        <div className="header-badge" id="header-badge">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
            <circle cx="5" cy="5" r="4" opacity="0.8"/>
          </svg>
          GraphRAG · 44,000 Issues
        </div>
        <h1 className="header-title">Redmine<br />Search</h1>
      </header>

      {/* Query Input */}
      <QueryInput
        value={query}
        onChange={setQuery}
        onSubmit={handleSubmit}
        isLoading={isLoading}
      />

      {/* Results area */}
      {hasResult && (
        <div className="answer-container">
          {/* Metadata strip */}
          <MetadataBadges
            parsed={parsed}
            fusedCount={fusedCount}
            elapsedMs={elapsedMs}
            isVisible={!!parsed || stage !== 'idle'}
          />

          {/* Error */}
          {error && (
            <div className="error-card" id="error-card" role="alert">
              <span className="error-icon">⚠️</span>
              <div>
                <div className="error-title">Pipeline Error</div>
                <div className="error-message">{error}</div>
              </div>
            </div>
          )}

          {/* Streaming answer */}
          <AnswerStream
            text={answer}
            isStreaming={isStreaming}
            isThinking={isThinking}
            stage={stage}
          />

          {/* Related issues */}
          <RelatedIssues
            issues={fusedIssues}
            isVisible={stage === 'done' && fusedIssues.length > 0}
          />
        </div>
      )}

      {/* Empty state */}
      {!hasResult && (
        <div className="empty-state" id="empty-state">
          <div className="empty-icon">🔍</div>
          <div className="empty-title">Ask anything about Redmine</div>
          <div className="empty-subtitle">
            Root causes, blocking chains, duplicate bugs, timeline analysis,
            attachment contents — all answered using 20 years of archived data.
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="footer" id="page-footer">
        Redmine GraphRAG · gemma4:e4b + qwen2.5-coder:7b · ChromaDB + Neo4j · Local AI
      </footer>
    </main>
  );
}
