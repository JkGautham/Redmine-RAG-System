'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import ChatSidebar from '@/components/ChatSidebar';
import ChatMessage from '@/components/ChatMessage';
import ChatInput, { EXAMPLE_QUERIES } from '@/components/ChatInput';
import type { ImageAttachment } from '@/components/ChatInput';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Stage = 'idle' | 'parsing' | 'retrieving' | 'compressing' | 'synthesizing' | 'done';

interface Message {
  id: number;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  ocr_text?: string | null;
  image_filename?: string | null;
  metadata?: any;
  created_at: string;
}

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export default function HomePage() {
  // Conversations state
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  // Streaming state
  const [streamingText, setStreamingText] = useState('');
  const [stage, setStage] = useState<Stage>('idle');
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // UI state
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Load conversations on mount ──
  useEffect(() => {
    fetchConversations();
  }, []);

  const fetchConversations = async () => {
    try {
      const resp = await fetch(`${API_URL}/conversations`);
      if (resp.ok) {
        const data = await resp.json();
        setConversations(data);
      }
    } catch (err) {
      console.error('Failed to fetch conversations:', err);
    }
  };

  const fetchMessages = async (convId: string) => {
    try {
      const resp = await fetch(`${API_URL}/conversations/${convId}`);
      if (resp.ok) {
        const data = await resp.json();
        setMessages(data.messages || []);
      }
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  };

  // ── Select conversation ──
  const selectConversation = useCallback(async (convId: string) => {
    setActiveConvId(convId);
    setSidebarOpen(false);
    await fetchMessages(convId);
    setStreamingText('');
    setStage('idle');
    setError(null);
  }, []);

  // ── Create new conversation ──
  const createNewChat = useCallback(async () => {
    try {
      const resp = await fetch(`${API_URL}/conversations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Chat' }),
      });
      if (resp.ok) {
        const conv = await resp.json();
        setConversations(prev => [conv, ...prev]);
        setActiveConvId(conv.id);
        setMessages([]);
        setStreamingText('');
        setStage('idle');
        setError(null);
        setSidebarOpen(false);
      }
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  }, []);

  // ── Delete conversation ──
  const deleteConversation = useCallback(async (convId: string) => {
    try {
      await fetch(`${API_URL}/conversations/${convId}`, { method: 'DELETE' });
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (activeConvId === convId) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err);
    }
  }, [activeConvId]);

  // ── Scroll to bottom ──
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingText, scrollToBottom]);

  // ── Send message ──
  const handleSend = useCallback(async (text: string, images: ImageAttachment[]) => {
    if (isLoading) return;

    let convId = activeConvId;

    // Auto-create conversation if none selected
    if (!convId) {
      try {
        const resp = await fetch(`${API_URL}/conversations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'New Chat' }),
        });
        if (resp.ok) {
          const conv = await resp.json();
          convId = conv.id;
          setConversations(prev => [conv, ...prev]);
          setActiveConvId(convId);
        }
      } catch (err) {
        setError('Failed to create conversation');
        return;
      }
    }

    if (!convId) return;

    // Collect OCR text from images
    const ocrTexts = images
      .filter(img => img.ocrText)
      .map(img => img.ocrText!);
    const combinedOcrText = ocrTexts.length > 0 ? ocrTexts.join('\n\n---\n\n') : undefined;

    // Optimistically add user message to UI
    const userMsg: Message = {
      id: Date.now(),
      conversation_id: convId,
      role: 'user',
      content: text,
      ocr_text: combinedOcrText || null,
      image_filename: images.length > 0 ? images[0].file.name : null,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);

    // Reset streaming state
    setStreamingText('');
    setError(null);
    setIsLoading(true);
    setIsThinking(false);
    setStage('parsing');

    try {
      // Use the chat-aware streaming endpoint
      const resp = await fetch(`${API_URL}/ask/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: text,
          conversation_id: convId,
          ocr_text: combinedOcrText || null,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullAnswer = '';
      let currentEvent = '';

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          
          // SSE format: "event: xxx\ndata: yyy\n\n"
          // Process complete SSE blocks (separated by double newlines)
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() || ''; // Keep incomplete block in buffer

          for (const block of blocks) {
            if (!block.trim()) continue;
            
            const lines = block.split('\n');
            let eventType = '';
            let dataStr = '';

            for (const line of lines) {
              if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();
              } else if (line.startsWith('data:')) {
                dataStr = line.slice(5).trim();
              }
            }

            switch (eventType) {
              case 'parsed':
                setStage('retrieving');
                break;
              case 'retrieved':
                setStage('synthesizing');
                setIsThinking(true);
                break;
              case 'context_ready':
                setStage('synthesizing');
                break;
              case 'token':
                setIsThinking(false);
                fullAnswer += dataStr;
                setStreamingText(fullAnswer);
                break;
              case 'done':
                setStage('done');
                setIsLoading(false);
                break;
            }
          }
        }
      }

      // Refresh messages from server to get proper IDs and metadata
      await fetchMessages(convId);
      setStreamingText('');
      setStage('idle');

    } catch (err: any) {
      // Fallback to non-streaming POST /ask
      try {
        const resp = await fetch(`${API_URL}/ask`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: text }),
        });
        if (resp.ok) {
          const data = await resp.json();
          // Refresh messages
          await fetchMessages(convId!);
          setStreamingText('');
        } else {
          setError(`Request failed: HTTP ${resp.status}`);
        }
      } catch (fallbackErr: any) {
        setError(fallbackErr.message || 'Request failed');
      }
    } finally {
      setIsLoading(false);
      setStage('idle');
      setIsThinking(false);
      // Refresh conversation list to update titles
      fetchConversations();
    }
  }, [activeConvId, isLoading]);

  // Handle example query click
  const handleExampleClick = useCallback((query: string) => {
    handleSend(query, []);
  }, [handleSend]);

  // Get active conversation title
  const activeConv = conversations.find(c => c.id === activeConvId);

  return (
    <>
      {/* Sidebar */}
      <ChatSidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={selectConversation}
        onNewChat={createNewChat}
        onDelete={deleteConversation}
        isOpen={sidebarOpen}
      />

      {/* Main chat area */}
      <main className="chat-main" id="main-content">
        {/* Chat Header */}
        <div className="chat-header">
          <button
            className="mobile-sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle sidebar"
          >
            ☰
          </button>
          <span className="chat-header-title">
            {activeConv ? activeConv.title : 'Redmine GraphRAG'}
          </span>
          <span className="chat-header-badge">
            <svg width="8" height="8" viewBox="0 0 10 10" fill="currentColor">
              <circle cx="5" cy="5" r="4"/>
            </svg>
            AI-Powered
          </span>
        </div>

        {/* Messages or Empty State */}
        {messages.length === 0 && !isLoading ? (
          <div className="chat-empty">
            <img src="/redmin_ai_logo.png" alt="Logo" className="chat-empty-icon" style={{ background: 'none', boxShadow: 'none' }} />
            <div className="chat-empty-title">Redmine GraphRAG</div>
            <div className="chat-empty-subtitle">
              Ask anything about 44,000 Redmine issues. Root causes, blocking chains,
              duplicate bugs, timeline analysis — powered by vector + graph fusion.
            </div>
            <div className="chat-empty-chips">
              {EXAMPLE_QUERIES.map((q, i) => (
                <button
                  key={i}
                  className="empty-chip"
                  onClick={() => handleExampleClick(q)}
                  id={`example-query-${i}`}
                >
                  {q.length > 55 ? q.slice(0, 55) + '…' : q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-messages" id="chat-messages">
            <div className="chat-messages-inner">
              {messages.map((msg) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  apiUrl={API_URL}
                />
              ))}

              {/* Streaming message (in progress) */}
              {isLoading && (
                <ChatMessage
                  message={{
                    id: -1,
                    conversation_id: activeConvId || '',
                    role: 'assistant',
                    content: '',
                    created_at: new Date().toISOString(),
                  }}
                  isStreaming={true}
                  isThinking={isThinking}
                  streamingText={streamingText}
                  stage={stage}
                  apiUrl={API_URL}
                />
              )}

              {/* Error */}
              {error && (
                <div className="error-card" role="alert">
                  <span className="error-icon">⚠️</span>
                  <div>
                    <div className="error-title">Pipeline Error</div>
                    <div className="error-message">{error}</div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* Chat Input */}
        <ChatInput
          onSend={handleSend}
          isLoading={isLoading}
          apiUrl={API_URL}
        />
      </main>
    </>
  );
}
