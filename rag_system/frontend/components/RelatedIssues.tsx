'use client';

interface RelatedIssue {
  issue_id: number;
  subject: string;
  status?: string;
  tracker?: string;
  rrf_score?: number;
}

interface RelatedIssuesProps {
  issues: RelatedIssue[];
  isVisible: boolean;
}

function statusClass(status?: string): string {
  if (!status) return 'status-other';
  const s = status.toLowerCase();
  if (s.includes('close') || s.includes('resolve') || s.includes('fix')) return 'status-closed';
  if (s.includes('open') || s.includes('new') || s.includes('progress')) return 'status-open';
  return 'status-other';
}

export default function RelatedIssues({ issues, isVisible }: RelatedIssuesProps) {
  if (!isVisible || issues.length === 0) return null;

  return (
    <div className="related-card glass-card" id="related-issues-card">
      <div className="related-header">
        <span>🔎</span> Related Issues — {issues.length} found via vector + graph fusion
      </div>
      <div className="related-list" role="list">
        {issues.slice(0, 8).map((issue, i) => (
          <div
            key={issue.issue_id}
            className="related-item"
            id={`related-issue-${issue.issue_id}`}
            role="listitem"
          >
            <span className="related-id">#{issue.issue_id}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="related-subject">{issue.subject || '(no subject)'}</div>
              {issue.tracker && (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                  {issue.tracker}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
              {issue.status && (
                <span className={`related-status ${statusClass(issue.status)}`}>
                  {issue.status}
                </span>
              )}
              {issue.rrf_score !== undefined && (
                <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono, monospace' }}>
                  {issue.rrf_score.toFixed(4)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
