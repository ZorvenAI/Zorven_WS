'use client';

import { FileText, Image, Film, Loader2, CheckCircle2, XCircle } from 'lucide-react';

export interface FileAttachment {
  id: number;
  file_name: string;
  file_type: string;
  file_size: number;
  pipeline_status: string;
  asset?: number | null;
}

interface FilePreviewProps {
  attachments: FileAttachment[];
  isUser?: boolean;
}

function getFileIcon(type: string) {
  if (type === 'image') return <Image className="w-4 h-4" />;
  if (type === 'video') return <Film className="w-4 h-4" />;
  return <FileText className="w-4 h-4" />;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'pending':
    case 'processing':
      return (
        <span className="flex items-center gap-1 text-[10px] text-brand-electric/60">
          <Loader2 className="w-3 h-3 animate-spin" />
          {status === 'pending' ? 'Queued' : 'Processing'}
        </span>
      );
    case 'indexed':
      return (
        <span className="flex items-center gap-1 text-[10px] text-brand-mint/70">
          <CheckCircle2 className="w-3 h-3" />
          Indexed
        </span>
      );
    case 'failed':
      return (
        <span className="flex items-center gap-1 text-[10px] text-red-400/70">
          <XCircle className="w-3 h-3" />
          Failed
        </span>
      );
    default:
      return null;
  }
}

export function FilePreview({ attachments, isUser = false }: FilePreviewProps) {
  if (!attachments || attachments.length === 0) return null;

  return (
    <div className="mt-2 space-y-1.5">
      {attachments.map((att) => (
        <div
          key={att.id}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
            isUser
              ? 'bg-brand-midnight/10 border border-brand-midnight/15'
              : 'bg-white/[0.03] border border-white/5'
          }`}
        >
          <span className={isUser ? 'text-brand-midnight/60' : 'text-brand-silver/50'}>
            {getFileIcon(att.file_type)}
          </span>
          <div className="flex-1 min-w-0">
            <p className={`text-xs truncate ${
              isUser ? 'text-brand-midnight' : 'text-brand-silver'
            }`}>{att.file_name}</p>
            <p className={`text-[10px] ${
              isUser ? 'text-brand-midnight/50' : 'text-brand-silver/30'
            }`}>
              {formatSize(att.file_size)}
            </p>
          </div>
          <StatusBadge status={att.pipeline_status} />
        </div>
      ))}
    </div>
  );
}
