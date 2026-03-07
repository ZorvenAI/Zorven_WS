'use client';

import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import { Paperclip, X, Send, FileText, Image, Film, Mic, MicOff, Loader2, Square } from 'lucide-react';
import { useVoiceInput } from '@/hooks/useVoiceInput';

interface PendingFile {
  file: File;
  id: string;
  preview?: string;
}

export interface ChatInputHandle {
  addFiles: (files: FileList | File[]) => void;
}

interface ChatInputProps {
  onSend: (message: string, files: File[]) => void;
  onCancel?: () => void;
  disabled?: boolean;
  isLoading?: boolean;
  isCancelling?: boolean;
  placeholder?: string;
  disabledTitle?: string;
  initialValue?: string;
  onNavigateUp?: () => string | null;
  onNavigateDown?: () => string | null;
  onExitHistory?: () => void;
  onDraftChange?: (text: string) => void;
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

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(function ChatInput(
  {
    onSend,
    onCancel,
    disabled = false,
    isLoading = false,
    isCancelling = false,
    placeholder = 'Ask me about your brand strategy...',
    disabledTitle,
    initialValue,
    onNavigateUp,
    onNavigateDown,
    onExitHistory,
    onDraftChange,
  },
  ref
) {
  const [input, setInput] = useState('');
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const voice = useVoiceInput();

  // Restore input when initialValue changes (e.g., after cancel)
  useEffect(() => {
    if (initialValue !== undefined && initialValue !== '') {
      setInput(initialValue);
      requestAnimationFrame(() => {
        const ta = textareaRef.current;
        if (ta) {
          ta.style.height = 'auto';
          ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
        }
      });
    }
  }, [initialValue]);

  // Append transcribed text to the textarea when voice input produces a result.
  useEffect(() => {
    if (!voice.transcript) return;
    setInput((prev) => {
      const sep = prev && !prev.endsWith(' ') ? ' ' : '';
      return prev + sep + voice.transcript;
    });
    voice.reset();
    // Auto-resize textarea after inserting transcribed text
    requestAnimationFrame(() => {
      const ta = textareaRef.current;
      if (ta) {
        ta.style.height = 'auto';
        ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice.transcript]);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const val = e.target.value;
      setInput(val);
      onDraftChange?.(val);
      const ta = e.target;
      ta.style.height = 'auto';
      ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
    },
    [onDraftChange]
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

  // Expose addFiles to parent via ref
  useImperativeHandle(ref, () => ({ addFiles }), [addFiles]);

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
        return;
      }

      // Up arrow — navigate input history
      if (e.key === 'ArrowUp' && onNavigateUp) {
        const ta = textareaRef.current;
        // Only trigger when cursor is at start or input is empty
        if (!input || (ta && ta.selectionStart === 0)) {
          const prev = onNavigateUp();
          if (prev !== null) {
            e.preventDefault();
            setInput(prev);
            requestAnimationFrame(() => {
              if (ta) {
                ta.style.height = 'auto';
                ta.style.height = `${Math.min(ta.scrollHeight, 144)}px`;
              }
            });
          }
        }
      }

      // Down arrow — navigate forward in history
      if (e.key === 'ArrowDown' && onNavigateDown) {
        const next = onNavigateDown();
        if (next !== null) {
          e.preventDefault();
          setInput(next);
        }
      }

      // Escape — exit history mode
      if (e.key === 'Escape' && onExitHistory) {
        onExitHistory();
      }
    },
    [handleSend, input, onNavigateUp, onNavigateDown, onExitHistory]
  );

  // Clipboard paste handler — intercept pasted images/files
  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      const files: File[] = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
          const file = items[i].getAsFile();
          if (file) files.push(file);
        }
      }

      if (files.length > 0) {
        e.preventDefault();
        addFiles(files);
      }
      // If no files, allow normal text paste (don't prevent default)
    },
    [addFiles]
  );

  return (
    <div className="shrink-0 bg-brand-midnight/80 backdrop-blur border-t border-white/10 px-4 sm:px-6 py-4">
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

      {/* Voice recording / transcribing indicator */}
      {voice.isListening && (
        <div className="flex items-center gap-2 mb-2 text-xs text-red-400">
          <span className="w-2 h-2 bg-red-400 rounded-full animate-pulse" />
          Recording&hellip; release to stop
        </div>
      )}
      {voice.isTranscribing && (
        <div className="flex items-center gap-2 mb-2 text-xs text-brand-electric/60">
          <Loader2 className="w-3 h-3 animate-spin" />
          Transcribing&hellip;
        </div>
      )}
      {voice.error && (
        <div className="mb-2 text-xs text-red-400">{voice.error}</div>
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
          onPaste={handlePaste}
          placeholder={disabled ? disabledTitle || placeholder : placeholder}
          className="input-dark flex-1 resize-none"
          rows={1}
          disabled={disabled}
        />

        {/* Voice input (hold-to-talk) */}
        {voice.isSupported && (
          <button
            onMouseDown={voice.startListening}
            onMouseUp={voice.stopListening}
            onMouseLeave={() => { if (voice.isListening) voice.stopListening(); }}
            onTouchStart={(e) => { e.preventDefault(); voice.startListening(); }}
            onTouchEnd={(e) => { e.preventDefault(); voice.stopListening(); }}
            onKeyDown={(e) => {
              if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                if (!voice.isListening && !disabled && !voice.isTranscribing) {
                  voice.startListening();
                }
              }
            }}
            onKeyUp={(e) => {
              if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                if (voice.isListening) voice.stopListening();
              }
            }}
            disabled={disabled || voice.isTranscribing}
            className={`p-2.5 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
              voice.isListening
                ? 'text-red-400 bg-red-500/20 animate-pulse'
                : voice.isTranscribing
                  ? 'text-brand-electric/60'
                  : 'text-brand-silver/40 hover:text-brand-silver hover:bg-white/5'
            }`}
            aria-label={
              voice.isListening
                ? 'Recording... release to stop'
                : voice.isTranscribing
                  ? 'Transcribing...'
                  : 'Hold to speak'
            }
            title={
              voice.isListening
                ? 'Recording...'
                : voice.isTranscribing
                  ? 'Transcribing...'
                  : 'Hold to speak'
            }
          >
            {voice.isTranscribing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : voice.isListening ? (
              <MicOff className="w-4 h-4" />
            ) : (
              <Mic className="w-4 h-4" />
            )}
          </button>
        )}

        {/* Send / Stop / Cancelling button */}
        {isLoading && !isCancelling ? (
          <button
            onClick={onCancel}
            className="btn-primary p-2.5 animate-pulse"
            aria-label="Stop generation"
            title="Stop generation"
          >
            <Square className="w-4 h-4" />
          </button>
        ) : isCancelling ? (
          <button
            disabled
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed p-2.5"
            aria-label="Cancelling..."
            title="Cancelling..."
          >
            <Loader2 className="w-4 h-4 animate-spin" />
          </button>
        ) : (
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
        )}
      </div>
    </div>
  );
});
