'use client';

import { useState, useRef, useCallback } from 'react';
import { Paperclip, X, Send, FileText, Image, Film } from 'lucide-react';

interface PendingFile {
  file: File;
  id: string;
  preview?: string;
}

interface ChatInputProps {
  onSend: (message: string, files: File[]) => void;
  disabled?: boolean;
  isLoading?: boolean;
  placeholder?: string;
  disabledTitle?: string;
}

const ALLOWED_TYPES = [
  'image/jpeg',
  'image/png',
  'image/gif',
  'image/webp',
  'video/mp4',
  'video/quicktime',
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
];

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

function getFileIcon(type: string) {
  if (type.startsWith('image/')) return <Image className="w-3.5 h-3.5" />;
  if (type.startsWith('video/')) return <Film className="w-3.5 h-3.5" />;
  return <FileText className="w-3.5 h-3.5" />;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ChatInput({
  onSend,
  disabled = false,
  isLoading = false,
  placeholder = 'Ask me about your brand strategy...',
  disabledTitle,
}: ChatInputProps) {
  const [input, setInput] = useState('');
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value);
      const ta = e.target;
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
    },
    []
  );

  const addFiles = useCallback((files: FileList | File[]) => {
    const newPending: PendingFile[] = [];
    for (const file of Array.from(files)) {
      if (!ALLOWED_TYPES.includes(file.type)) {
        continue; // Skip unsupported types silently
      }
      if (file.size > MAX_FILE_SIZE) {
        continue; // Skip oversized files
      }
      const pf: PendingFile = {
        file,
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      };
      if (file.type.startsWith('image/')) {
        pf.preview = URL.createObjectURL(file);
      }
      newPending.push(pf);
    }
    if (newPending.length > 0) {
      setPendingFiles((prev) => [...prev, ...newPending]);
    }
  }, []);

  const removeFile = useCallback((id: string) => {
    setPendingFiles((prev) => {
      const removed = prev.find((f) => f.id === id);
      if (removed?.preview) URL.revokeObjectURL(removed.preview);
      return prev.filter((f) => f.id !== id);
    });
  }, []);

  const handleSend = useCallback(() => {
    if (!input.trim() && pendingFiles.length === 0) return;
    onSend(input, pendingFiles.map((pf) => pf.file));
    setInput('');
    // Revoke all object URLs
    pendingFiles.forEach((pf) => {
      if (pf.preview) URL.revokeObjectURL(pf.preview);
    });
    setPendingFiles([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, pendingFiles, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  // Drag-and-drop handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles]
  );

  return (
    <div
      className={`shrink-0 bg-brand-midnight/80 backdrop-blur border-t border-white/10 px-4 sm:px-6 py-4 ${
        dragOver ? 'ring-2 ring-brand-electric/40 ring-inset' : ''
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Pending file chips */}
      {pendingFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-3">
          {pendingFiles.map((pf) => (
            <div
              key={pf.id}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-brand-silver"
            >
              {pf.preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={pf.preview}
                  alt={pf.file.name}
                  className="w-5 h-5 rounded object-cover"
                />
              ) : (
                getFileIcon(pf.file.type)
              )}
              <span className="max-w-[120px] truncate">{pf.file.name}</span>
              <span className="text-brand-silver/40">
                {formatSize(pf.file.size)}
              </span>
              <button
                onClick={() => removeFile(pf.id)}
                aria-label={`Remove ${pf.file.name}`}
                className="ml-0.5 p-0.5 rounded hover:bg-white/10 text-brand-silver/40 hover:text-white transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-end space-x-3 sm:space-x-4">
        {/* File attach button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="p-2.5 rounded-lg text-brand-silver/40 hover:text-brand-silver hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Attach file"
          title="Attach file"
        >
          <Paperclip className="w-4 h-4" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_TYPES.join(',')}
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = '';
          }}
        />

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? disabledTitle || placeholder : placeholder}
          className="input-dark flex-1 resize-none"
          rows={1}
          disabled={disabled}
        />

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={
            disabled ||
            isLoading ||
            (!input.trim() && pendingFiles.length === 0)
          }
          className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed p-2.5"
          aria-label="Send message"
          title={disabledTitle}
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
