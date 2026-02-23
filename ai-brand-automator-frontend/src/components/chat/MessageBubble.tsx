'use client';

import { usePollingJob } from '@/hooks/usePollingJob';
import ThoughtTrace from '@/components/pipelines/ThoughtTrace';
import ResultDashboard from '@/components/pipelines/ResultDashboard';
import { Loader2 } from 'lucide-react';

export interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
  pipelineJobId?: string | null;
}

export interface MessageBubbleProps {
  message: Message;
}

function PipelineInlineCard({ jobId }: { jobId: string }) {
  const { job, isLoading } = usePollingJob(jobId);

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
      {/* Running: show ThoughtTrace */}
      {(job.status === 'queued' || job.status === 'running') && (
        <div className="p-3">
          <ThoughtTrace progress={job.progress} jobStatus={job.status} />
        </div>
      )}

      {/* Completed: show ResultDashboard */}
      {job.status === 'completed' && job.result_data && (
        <div className="p-3">
          <ResultDashboard
            resultData={job.result_data}
            manifestName={job.manifest_name}
          />
        </div>
      )}

      {/* Failed */}
      {job.status === 'failed' && (
        <div className="p-3 text-xs text-red-400">
          Analysis failed: {job.error_message || 'Unknown error'}
        </div>
      )}
    </div>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  return (
    <div className={`flex ${message.isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-xs lg:max-w-md ${message.pipelineJobId ? 'xl:max-w-2xl' : ''} px-4 py-2 rounded-lg ${
          message.isUser
            ? 'bg-brand-electric text-brand-midnight'
            : 'bg-white/5 border border-white/10 text-white'
        }`}
      >
        <p className="text-sm">{message.content}</p>
        <p suppressHydrationWarning className={`text-xs mt-1 ${message.isUser ? 'text-brand-midnight/60' : 'text-brand-silver/50'}`}>
          {message.timestamp.toLocaleTimeString()}
        </p>
        {message.pipelineJobId && (
          <PipelineInlineCard jobId={message.pipelineJobId} />
        )}
      </div>
    </div>
  );
}
