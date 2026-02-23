'use client';

import { useState, useEffect } from 'react';
import { MessageBubble } from './MessageBubble';
import { FileSearch } from './FileSearch';
import { apiClient } from '@/lib/api';
import { useTenantRole } from '@/hooks/useTenantRole';

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
  pipelineJobId?: string | null;
}

export function ChatInterface() {
  const { canEdit: canEditFlag } = useTenantRole();
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => { requestAnimationFrame(() => setHasMounted(true)); }, []);
  const canEdit = hasMounted ? canEditFlag : false;
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      content: 'Hello! I\'m your AI brand assistant. How can I help you with your brand strategy today?',
      isUser: false,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: input,
      isUser: true,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const body: Record<string, string> = { message: input };
      if (sessionId) {
        body.session_id = sessionId;
      }
      const response = await apiClient.post('/ai/chat/', body);

      if (response.ok) {
        const data = await response.json();
        // Persist session_id for conversation continuity
        if (data.session_id && !sessionId) {
          setSessionId(data.session_id);
        }
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: data.response || 'I understand you\'re asking about brand strategy. Let me analyze your company data and provide some insights.',
          isUser: false,
          timestamp: new Date(),
          pipelineJobId: data.pipeline_job?.job_id ?? null,
        };
        setMessages(prev => [...prev, aiMessage]);
      } else {
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: 'Sorry, I encountered an error. Please try again.',
          isUser: false,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, aiMessage]);
      }
    } catch (error) {
      console.error('AI chat error:', error);
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: 'Sorry, I encountered an error. Please try again.',
        isUser: false,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, aiMessage]);
    }
    setIsLoading(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="shrink-0 bg-brand-midnight/80 backdrop-blur border-b border-white/10 px-4 sm:px-6 py-3 sm:py-4">
          <div>
            <h1 className="text-lg sm:text-xl font-heading font-semibold text-white truncate">AI Brand Assistant</h1>
            <p className="text-xs sm:text-sm text-brand-silver/70 hidden sm:block">Ask anything about your brand or run an analysis pipeline</p>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4 bg-brand-midnight">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
          {isLoading && (
            <div className="flex justify-start">
              <div className="bg-white/5 border border-white/10 rounded-lg px-4 py-2">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-brand-electric rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-brand-electric rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-brand-electric rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="shrink-0 bg-brand-midnight/80 backdrop-blur border-t border-white/10 px-4 sm:px-6 py-4">
          <div className="flex space-x-3 sm:space-x-4">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={canEdit ? 'Ask me about your brand strategy...' : 'You need editor access to use the AI chat'}
              className="input-dark flex-1 resize-none"
              rows={1}
              disabled={!canEdit}
            />
            <button
              onClick={handleSend}
              disabled={!canEdit || isLoading || !input.trim()}
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              title={!canEdit ? 'You need editor access to send messages' : undefined}
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* File Search Sidebar — hidden on small screens */}
      <div className="hidden xl:block w-80 shrink-0 bg-brand-midnight border-l border-white/10 overflow-y-auto">
        <FileSearch />
      </div>
    </div>
  );
}