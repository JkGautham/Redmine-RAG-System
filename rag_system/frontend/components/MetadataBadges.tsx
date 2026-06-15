'use client';

interface ParsedQuery {
  intent?: string;
  complexity?: string;
  needs_graph?: boolean;
  needs_attachments?: boolean;
  entities?: { issue_ids?: number[] };
}

interface MetadataBadgesProps {
  parsed: ParsedQuery | null;
  fusedCount: number;
  elapsedMs: number;
  isVisible: boolean;
}

export default function MetadataBadges({ parsed, fusedCount, elapsedMs, isVisible }: MetadataBadgesProps) {
  if (!isVisible || !parsed) return null;

  const intent     = parsed.intent || 'hybrid';
  const complexity = parsed.complexity || 'moderate';
  const issueIds   = parsed.entities?.issue_ids || [];

  return (
    <div className="metadata-strip" id="metadata-strip" role="status" aria-label="Query analysis">
      <span className="metadata-label">Query:</span>

      {/* Intent badge */}
      <span className={`badge badge-intent`} id="badge-intent">
        {intentIcon(intent)} {intent.replace('_', ' ')}
      </span>

      {/* Complexity badge */}
      <span className={`badge badge-complexity-${complexity}`} id="badge-complexity">
        {complexityIcon(complexity)} {complexity}
      </span>

      {/* Graph badge */}
      {parsed.needs_graph && (
        <span className="badge" id="badge-graph" style={{ background: 'rgba(104,211,145,0.1)', border: '1px solid rgba(104,211,145,0.2)', color: 'var(--accent-emerald)' }}>
          🔗 graph
        </span>
      )}

      {/* Attachments badge */}
      {parsed.needs_attachments && (
        <span className="badge" id="badge-attachments" style={{ background: 'rgba(246,173,85,0.1)', border: '1px solid rgba(246,173,85,0.2)', color: 'var(--accent-amber)' }}>
          📎 attachments
        </span>
      )}

      {/* Issue IDs */}
      {issueIds.length > 0 && (
        <span className="badge badge-count" id="badge-issue-ids">
          #{issueIds.slice(0, 3).join(', #')}{issueIds.length > 3 ? '…' : ''}
        </span>
      )}

      {/* Fused count */}
      {fusedCount > 0 && (
        <span className="badge badge-count" id="badge-fused">
          {fusedCount} issues fused
        </span>
      )}

      {/* Elapsed time */}
      {elapsedMs > 0 && (
        <span className="badge-time" id="badge-elapsed">
          ⏱ {(elapsedMs / 1000).toFixed(1)}s
        </span>
      )}
    </div>
  );
}

function intentIcon(intent: string): string {
  return ({
    root_cause: '🔍',
    dependency: '🔗',
    timeline:   '📅',
    similar:    '🪞',
    attachment: '📎',
    hybrid:     '⚡',
  } as Record<string, string>)[intent] || '⚡';
}

function complexityIcon(complexity: string): string {
  return ({ simple: '●', moderate: '●●', complex: '●●●' } as Record<string, string>)[complexity] || '●';
}
