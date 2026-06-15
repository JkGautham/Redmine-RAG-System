'use client';

import { useRef, useEffect, KeyboardEvent } from 'react';

const EXAMPLE_QUERIES = [
  'Why was the project creation bug fixed after 3 months?',
  'What issues block #44132?',
  'Find duplicate bugs related to email notifications',
  'How did the permissions system evolve since 2010?',
];

interface QueryInputProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

export default function QueryInput({ value, onChange, onSubmit, isLoading }: QueryInputProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (!isLoading && value.trim()) onSubmit();
    }
  };

  return (
    <div className="query-form glass-card" style={{ padding: '20px 24px 16px' }}>
      <div className="query-wrapper">
        <textarea
          ref={ref}
          id="query-input"
          className="query-input"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKey}
          placeholder={'Ask anything about 44,000 Redmine issues… e.g. "Why did issue #44132 take 3 months?"'}
          rows={2}
          disabled={isLoading}
          autoFocus
        />
        <button
          id="submit-query-btn"
          className="query-submit-btn"
          onClick={onSubmit}
          disabled={isLoading || !value.trim()}
          aria-label="Submit query"
        >
          {isLoading ? (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round"/>
              </svg>
              Thinking…
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 19-7z" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Ask <span style={{ opacity: 0.6, fontSize: '11px', marginLeft: 2 }}>⌘↵</span>
            </>
          )}
        </button>
      </div>

      <div className="example-queries">
        <span className="metadata-label" style={{ marginTop: 2 }}>Try:</span>
        {EXAMPLE_QUERIES.map((q, i) => (
          <button
            key={i}
            id={`example-query-${i}`}
            className="example-chip"
            onClick={() => { onChange(q); setTimeout(() => ref.current?.focus(), 0); }}
            disabled={isLoading}
          >
            {q.length > 50 ? q.slice(0, 50) + '…' : q}
          </button>
        ))}
      </div>
    </div>
  );
}
