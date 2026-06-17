'use client';

import { useEffect, useRef } from 'react';

interface MessageData {
  id: number;
  conversation_id?: string;
  role: 'user' | 'assistant';
  content: string;
  ocr_text?: string | null;
  image_filename?: string | null;
  metadata?: {
    parsed?: {
      intent?: string;
      complexity?: string;
      needs_graph?: boolean;
      needs_attachments?: boolean;
      entities?: { issue_ids?: number[] };
    };
    fused_count?: number;
  } | null;
  created_at: string;
}

interface ChatMessageProps {
  message: MessageData;
  isStreaming?: boolean;
  isThinking?: boolean;
  streamingText?: string;
  stage?: string;
  apiUrl: string;
}

// Highlight issue IDs like #12345 in the text
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
  { key: 'synthesizing', label: 'Synthesize' },
  { key: 'done',         label: 'Done' },
] as const;

const STAGE_ORDER = ['idle', 'parsing', 'retrieving', 'compressing', 'synthesizing', 'done'];

function formatTime(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export default function ChatMessage({
  message,
  isStreaming = false,
  isThinking = false,
  streamingText,
  stage,
  apiUrl
}: ChatMessageProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isStreaming) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [streamingText, isStreaming]);

  const isUser = message.role === 'user';
  const displayText = isStreaming && streamingText !== undefined ? streamingText : message.content;
  const stageIdx = stage ? STAGE_ORDER.indexOf(stage) : -1;

  return (
    <div className={`message-row ${message.role}`} id={`message-${message.id}`}>
      {/* Avatar */}
      {!isUser && (
        <div className="message-avatar assistant-avatar" aria-hidden="true">🤖</div>
      )}

      <div className="message-bubble">
        {/* User image attachment */}
        {isUser && message.image_filename && (
          <img
            src={`${apiUrl}/uploads/${message.image_filename}`}
            alt="Attached image"
            className="message-image"
          />
        )}

        {/* OCR indicator */}
        {isUser && message.ocr_text && (
          <div className="message-ocr-badge">
            📄 Image content extracted
          </div>
        )}

        {/* Message content */}
        <div className="message-content">
          {/* Stage progress for streaming assistant messages */}
          {!isUser && isStreaming && stage && stage !== 'idle' && stage !== 'done' && (
            <div className="stage-bar" style={{ paddingBottom: 12 }}>
              {STAGES.map((s, i) => {
                const sIdx = STAGE_ORDER.indexOf(s.key);
                const isDone = stageIdx > sIdx;
                const isActive = stageIdx === sIdx;
                return (
                  <div key={s.key} className="stage-step" style={{ flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                    <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                      <div className={`stage-dot ${isDone ? 'done' : isActive ? 'active' : 'pending'}`} />
                      {i < STAGES.length - 1 && (
                        <div className={`stage-line ${isDone ? 'done' : ''}`} />
                      )}
                    </div>
                    <span className="stage-label" style={{
                      color: isDone ? 'var(--accent-emerald)' : isActive ? 'var(--accent-cyan)' : 'var(--text-muted)'
                    }}>
                      {s.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Thinking indicator */}
          {!isUser && isThinking && (
            <div className="thinking-indicator">
              <div className="thinking-dots"><span /><span /><span /></div>
              <span>Reasoning through the evidence…</span>
            </div>
          )}

          {/* Skeleton while retrieving */}
          {!isUser && isStreaming && stage === 'retrieving' && !displayText && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div className="skeleton skeleton-line" style={{ width: '85%' }} />
              <div className="skeleton skeleton-line" style={{ width: '70%' }} />
              <div className="skeleton skeleton-line" style={{ width: '90%' }} />
            </div>
          )}

          {/* Text content */}
          {displayText && (
            <div className="answer-text">
              <HighlightedText text={displayText} />
              {isStreaming && <span className="cursor-blink" aria-hidden="true" />}
            </div>
          )}

          {/* Metadata badges for completed assistant messages */}
          {!isUser && !isStreaming && message.metadata?.parsed && (
            <div className="metadata-strip">
              <span className="metadata-label">Analysis:</span>
              {message.metadata.parsed.intent && (
                <span className="badge badge-intent">
                  {message.metadata.parsed.intent.replace('_', ' ')}
                </span>
              )}
              {message.metadata.parsed.complexity && (
                <span className={`badge badge-complexity-${message.metadata.parsed.complexity}`}>
                  {message.metadata.parsed.complexity}
                </span>
              )}
              {message.metadata.fused_count && message.metadata.fused_count > 0 && (
                <span className="badge badge-count">
                  {message.metadata.fused_count} issues
                </span>
              )}
            </div>
          )}
        </div>

        <div className="message-timestamp">{formatTime(message.created_at)}</div>
        <div ref={bottomRef} />
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="message-avatar user-avatar" aria-hidden="true">👤</div>
      )}
    </div>
  );
}
