'use client';

import { useEffect, useRef, useMemo } from 'react';

interface AnswerStreamProps {
  text: string;
  isStreaming: boolean;
  isThinking: boolean;
  stage: 'idle' | 'parsing' | 'retrieving' | 'compressing' | 'synthesizing' | 'done';
}

// Highlight issue IDs like #12345 in the answer text
function HighlightedText({ text }: { text: string }) {
  const parts = text.split(/(Issue\s*#\d+|#\d+)/gi);
  return (
    <>
      {parts.map((part, i) =>
        /^(Issue\s*#\d+|#\d+)$/i.test(part) ? (
          <span key={i} className="issue-ref">{part}</span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

const STAGES = [
  { key: 'parsing',      label: 'Parse' },
  { key: 'retrieving',   label: 'Retrieve' },
  { key: 'compressing',  label: 'Compress' },
  { key: 'synthesizing', label: 'Synthesize' },
  { key: 'done',         label: 'Done' },
] as const;

const STAGE_ORDER = ['idle', 'parsing', 'retrieving', 'compressing', 'synthesizing', 'done'];

export default function AnswerStream({ text, isStreaming, isThinking, stage }: AnswerStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const stageIdx = STAGE_ORDER.indexOf(stage);

  // Auto-scroll as text streams in
  useEffect(() => {
    if (isStreaming) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [text, isStreaming]);

  const isEmpty = !text && !isStreaming && !isThinking && stage === 'idle';
  if (isEmpty) return null;

  return (
    <div className="answer-card glass-card" id="answer-card">
      {/* Stage progress bar */}
      {stage !== 'idle' && stage !== 'done' && (
        <div className="stage-bar" style={{ paddingBottom: 20 }}>
          {STAGES.map((s, i) => {
            const sIdx = STAGE_ORDER.indexOf(s.key);
            const isDone   = stageIdx > sIdx;
            const isActive = stageIdx === sIdx;
            return (
              <div key={s.key} className="stage-step" style={{ flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                  <div className={`stage-dot ${isDone ? 'done' : isActive ? 'active' : 'pending'}`} />
                  {i < STAGES.length - 1 && (
                    <div className={`stage-line ${isDone ? 'done' : ''}`} />
                  )}
                </div>
                <span className="stage-label" style={{ color: isDone ? 'var(--accent-emerald)' : isActive ? 'var(--accent-primary)' : 'var(--text-muted)' }}>
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      )}

      <div className="answer-header">
        <div className="answer-header-icon">🤖</div>
        <div className="answer-header-title">AI Analysis</div>
        {isStreaming && (
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
            <div className="thinking-dots">
              <span /><span /><span />
            </div>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Generating…</span>
          </div>
        )}
      </div>

      {/* Thinking indicator */}
      {isThinking && (
        <div className="thinking-indicator">
          <div className="thinking-dots"><span /><span /><span /></div>
          <span>Reasoning through the evidence…</span>
        </div>
      )}

      {/* Skeleton while retrieving */}
      {stage === 'retrieving' && !text && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div className="skeleton skeleton-line" style={{ width: '85%' }} />
          <div className="skeleton skeleton-line" style={{ width: '70%' }} />
          <div className="skeleton skeleton-line" style={{ width: '90%' }} />
          <div className="skeleton skeleton-line" style={{ width: '55%' }} />
        </div>
      )}

      {/* Answer text */}
      {text && (
        <div className="answer-text" id="answer-text">
          <HighlightedText text={text} />
          {isStreaming && <span className="cursor-blink" aria-hidden="true" />}
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
