'use client';

import { useState } from 'react';
import { usePollingJob } from '@/hooks/usePollingJob';
import ThoughtTrace from '@/components/pipelines/ThoughtTrace';
import ResultDashboard from '@/components/pipelines/ResultDashboard';
import { MarkdownMessage } from './MarkdownMessage';
import { ThinkingBubble } from './ThinkingBubble';
import { FilePreview, type FileAttachment } from './FilePreview';
import { Loader2, ClipboardCopy, Check } from 'lucide-react';

export interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
  thinking?: string;
  pipelineJobId?: string | null;
  attachments?: FileAttachment[];
}

export interface MessageBubbleProps {
  message: Message;
}

function PipelineInlineCard({ jobId }: { jobId: string }) {
  const { job, quickStatus, isLoading } = usePollingJob(jobId);

  if (isLoading && !job) {
    return (
      <div className="mt-3 p-3 rounded-lg bg-white/5 border border-white/10">
        <div className="flex items-center gap-2 text-xs text-brand-silver/60">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Starting pipeline...
        </div>
      </div>
    );
  }

  if (!job) return null;

  return (
    <div className="mt-3 rounded-lg bg-white/5 border border-white/10 overflow-hidden">
      {(job.status === 'queued' || job.status === 'running') && (
        <div className="p-3">
          <ThoughtTrace
            progress={quickStatus?.progress ?? job.progress}
            jobStatus={job.status}
            lastThought={quickStatus?.last_thought}
            progressPercent={quickStatus?.progress_percent}
          />
        </div>
      )}
      {job.status === 'completed' && job.result_data && (
        <div className="p-3">
          <ResultDashboard
            resultData={job.result_data}
            manifestName={job.manifest_name}
          />
        </div>
      )}
      {job.status === 'failed' && (
        <div className="p-3 text-xs text-red-400">
          Analysis failed: {job.error_message || 'Unknown error'}
        </div>
      )}
    </div>
  );
}

function timeAgo(date: Date): string {
  const now = Date.now();
  const diff = now - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return date.toLocaleDateString();
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API may fail in non-secure contexts
    }
  };

  return (
    <div
      className={`group flex ${message.isUser ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`relative ${
          message.isUser
            ? 'max-w-xs lg:max-w-md'
            : `max-w-xl lg:max-w-2xl ${message.pipelineJobId ? 'xl:max-w-3xl' : ''}`
        } px-4 py-2.5 rounded-lg ${
          message.isUser
            ? 'bg-brand-electric text-brand-midnight'
            : 'bg-white/5 border border-white/10 text-brand-silver'
        }`}
      >
        {/* Thinking display for AI messages */}
        {!message.isUser && message.thinking && (
          <ThinkingBubble thinking={message.thinking} />
        )}

        {/* Message content */}
        {message.isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <MarkdownMessage content={message.content} />
        )}

        {/* Footer: timestamp + copy */}
        <div className="flex items-center justify-between mt-1.5 gap-2">
          <p
            suppressHydrationWarning
            className={`text-[10px] ${
              message.isUser
                ? 'text-brand-midnight/50'
                : 'text-brand-silver/30'
            }`}
          >
            {timeAgo(message.timestamp)}
          </p>

          {/* Copy button for AI messages */}
          {!message.isUser && (
            <button
              onClick={handleCopy}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-brand-silver/30 hover:text-brand-silver/60"
              aria-label="Copy message"
              title="Copy message"
            >
              {copied ? (
                <Check className="w-3 h-3" />
              ) : (
                <ClipboardCopy className="w-3 h-3" />
              )}
            </button>
          )}
        </div>

        {/* File attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <FilePreview attachments={message.attachments} isUser={message.isUser} />
        )}

        {/* Pipeline inline card */}
        {message.pipelineJobId && (
          <PipelineInlineCard jobId={message.pipelineJobId} />
        )}
      </div>
    </div>
  );
}
