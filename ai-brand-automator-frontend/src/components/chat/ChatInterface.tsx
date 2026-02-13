'use client';

import { useState } from 'react';
import Link from 'next/link';
import { MessageBubble } from './MessageBubble';
import { FileSearch } from './FileSearch';
import { apiClient } from '@/lib/api';
import { useTenantRole } from '@/hooks/useTenantRole';

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
}

export function ChatInterface() {
  const { canEdit } = useTenantRole();
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
      const response = await apiClient.post('/ai/chat/', { message: input });

      if (response.ok) {
        const data = await response.json();
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          content: data.response || 'I understand you\'re asking about brand strategy. Let me analyze your company data and provide some insights.',
          isUser: false,
          timestamp: new Date(),
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
    <div className="flex h-full">
      {/* Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="bg-brand-midnight/80 backdrop-blur border-b border-white/10 px-4 sm:px-6 py-3 sm:py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h1 className="text-lg sm:text-xl font-heading font-semibold text-white truncate">AI Brand Assistant</h1>
              <p className="text-xs sm:text-sm text-brand-silver/70 hidden sm:block">Get insights and generate content for your brand</p>
            </div>
            <Link 
              href="/dashboard" 
              className="flex items-center gap-1 sm:gap-2 text-brand-silver hover:text-brand-electric transition-colors text-xs sm:text-sm flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              <span className="hidden sm:inline">Back to Dashboard</span>
              <span className="sm:hidden">Back</span>
            </Link>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4 bg-brand-midnight">
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
        <div className="bg-brand-midnight/80 backdrop-blur border-t border-white/10 px-6 py-4">
          <div className="flex space-x-4">
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

      {/* File Search Sidebar */}
      <div className="w-80 bg-brand-midnight border-l border-white/10">
        <FileSearch />
      </div>
    </div>
  );
}