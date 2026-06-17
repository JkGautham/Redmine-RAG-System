'use client';

import { useMemo } from 'react';

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface ChatSidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onDelete: (id: string) => void;
  isOpen: boolean;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHrs = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHrs < 24) return `${diffHrs}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function groupConversations(conversations: Conversation[]) {
  const now = new Date();
  const today: Conversation[] = [];
  const yesterday: Conversation[] = [];
  const thisWeek: Conversation[] = [];
  const older: Conversation[] = [];

  for (const conv of conversations) {
    const date = new Date(conv.updated_at);
    const diffDays = Math.floor((now.getTime() - date.getTime()) / 86400000);

    if (diffDays < 1) today.push(conv);
    else if (diffDays < 2) yesterday.push(conv);
    else if (diffDays < 7) thisWeek.push(conv);
    else older.push(conv);
  }

  return { today, yesterday, thisWeek, older };
}

export default function ChatSidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
  isOpen
}: ChatSidebarProps) {
  const groups = useMemo(() => groupConversations(conversations), [conversations]);

  const renderGroup = (label: string, items: Conversation[]) => {
    if (items.length === 0) return null;
    return (
      <div key={label}>
        <div className="sidebar-section-label">{label}</div>
        {items.map(conv => (
          <div
            key={conv.id}
            className={`conv-item ${conv.id === activeId ? 'active' : ''}`}
            onClick={() => onSelect(conv.id)}
            id={`conv-${conv.id}`}
          >
            <div className="conv-item-icon">💬</div>
            <div className="conv-item-content">
              <div className="conv-item-title">{conv.title}</div>
              <div className="conv-item-meta">
                {conv.message_count} msgs · {formatRelativeTime(conv.updated_at)}
              </div>
            </div>
            <button
              className="conv-item-delete"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(conv.id);
              }}
              aria-label={`Delete conversation: ${conv.title}`}
              title="Delete"
            >
              🗑
            </button>
          </div>
        ))}
      </div>
    );
  };

  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`} id="chat-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <img src="/redmin_ai_logo.png" alt="Logo" className="sidebar-brand-icon" style={{ background: 'none', boxShadow: 'none', padding: '2px' }} />
          <div>
            <div className="sidebar-brand-text">Redmine GraphRAG</div>
            <div className="sidebar-brand-sub">44,000 Issues</div>
          </div>
        </div>
        <button
          className="new-chat-btn"
          onClick={onNewChat}
          id="new-chat-btn"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 5v14M5 12h14" strokeLinecap="round" />
          </svg>
          New Chat
        </button>
      </div>

      <div className="sidebar-conversations">
        {conversations.length === 0 ? (
          <div style={{
            padding: '40px 16px',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: '13px'
          }}>
            <div style={{ fontSize: '28px', marginBottom: '8px', opacity: 0.3 }}>💬</div>
            No conversations yet.
            <br />Start a new chat!
          </div>
        ) : (
          <>
            {renderGroup('Today', groups.today)}
            {renderGroup('Yesterday', groups.yesterday)}
            {renderGroup('This Week', groups.thisWeek)}
            {renderGroup('Older', groups.older)}
          </>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-footer-badge">
          <svg width="8" height="8" viewBox="0 0 10 10" fill="currentColor">
            <circle cx="5" cy="5" r="4" opacity="0.8"/>
          </svg>
          GraphRAG Active
        </div>
        <div>qwen3:8b · ChromaDB · Neo4j</div>
      </div>
    </aside>
  );
}
