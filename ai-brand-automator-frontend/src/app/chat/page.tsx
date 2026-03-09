'use client';

import { Suspense } from 'react';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { useAuth } from '@/hooks/useAuth';

export default function ChatPage() {
  useAuth(); // Protect this route
  return (
    <div className="h-[calc(100vh-3.5rem)] bg-brand-midnight">
      <Suspense>
        <ChatInterface />
      </Suspense>
    </div>
  );
}