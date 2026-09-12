'use client';

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ArrowDown, ArrowUp, ChevronDown, Search, Shield } from 'lucide-react';
import { formatTime, type TranscriptSegment } from '@/lib/onboarding-sessions';

const SPEAKER_COLORS: Record<number, string> = {
  0: 'text-brand-electric',
  1: 'text-emerald-400',
};

function speakerLabel(speaker: number): string {
  return `Speaker ${speaker + 1}`;
}

function speakerColor(speaker: number): string {
  return SPEAKER_COLORS[speaker] ?? 'text-brand-silver';
}

export interface TranscriptViewProps {
  segments: TranscriptSegment[];
  currentTime: number;
  onSeek: (t: number) => void;
  initialTime?: number;
}

interface SearchMatch {
  segmentIndex: number;
  charStart: number;
  charEnd: number;
}

function findMatches(
  segments: TranscriptSegment[],
  query: string,
): SearchMatch[] {
  if (!query) return [];
  const lower = query.toLowerCase();
  const results: SearchMatch[] = [];
  for (let i = 0; i < segments.length; i++) {
    const text = segments[i].text.toLowerCase();
    let start = 0;
    while (true) {
      const idx = text.indexOf(lower, start);
      if (idx === -1) break;
      results.push({
        segmentIndex: i,
        charStart: idx,
        charEnd: idx + lower.length,
      });
      start = idx + 1;
    }
  }
  return results;
}

function highlightText(
  text: string,
  matches: SearchMatch[],
  segmentIndex: number,
  activeMatchIndex: number,
  allMatches: SearchMatch[],
): React.ReactNode {
  const segMatches = matches.filter((m) => m.segmentIndex === segmentIndex);
  if (segMatches.length === 0) return text;

  const parts: React.ReactNode[] = [];
  let cursor = 0;

  for (const match of segMatches) {
    if (match.charStart > cursor) {
      parts.push(text.slice(cursor, match.charStart));
    }
    const globalIdx = allMatches.indexOf(match);
    const isActive = globalIdx === activeMatchIndex;
    parts.push(
      <mark
        key={`${match.charStart}-${match.charEnd}`}
        className={
          isActive
            ? 'rounded bg-brand-electric/40 text-white'
            : 'rounded bg-white/20 text-white'
        }
        data-match-index={globalIdx}
      >
        {text.slice(match.charStart, match.charEnd)}
      </mark>,
    );
    cursor = match.charEnd;
  }
  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }
  return parts;
}

export default function TranscriptView({
  segments,
  currentTime,
  onSeek,
  initialTime,
}: TranscriptViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const segmentRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [autoFollow, setAutoFollow] = useState(true);
  const programmaticScroll = useRef(false);
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [activeMatchIndex, setActiveMatchIndex] = useState(0);
  const [searchOpen, setSearchOpen] = useState(false);
  const hasRedactions = useMemo(
    () => segments.some((s) => s.redaction_applied),
    [segments],
  );
  const prevQueryRef = useRef(searchQuery);

  const matches = useMemo(
    () => findMatches(segments, searchQuery),
    [segments, searchQuery],
  );

  const currentSegmentIndex = useMemo(() => {
    for (let i = segments.length - 1; i >= 0; i--) {
      if (segments[i].t_start <= currentTime) return i;
    }
    return -1;
  }, [segments, currentTime]);

  useEffect(() => {
    if (!autoFollow || currentSegmentIndex < 0) return;
    const el = segmentRefs.current.get(currentSegmentIndex);
    if (!el || !containerRef.current) return;

    if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
    programmaticScroll.current = true;
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    scrollTimerRef.current = setTimeout(() => {
      programmaticScroll.current = false;
      scrollTimerRef.current = null;
    }, 300);
    return () => {
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
        scrollTimerRef.current = null;
      }
    };
  }, [currentSegmentIndex, autoFollow]);

  useEffect(() => {
    if (initialTime == null || segments.length === 0) return;
    const idx = segments.findIndex(
      (s) => s.t_start <= initialTime && s.t_end > initialTime,
    );
    if (idx >= 0) {
      const el = segmentRefs.current.get(idx);
      el?.scrollIntoView({ behavior: 'auto', block: 'center' });
    }
  }, [initialTime, segments]);

  const handleScroll = useCallback(() => {
    if (programmaticScroll.current) return;
    setAutoFollow(false);
  }, []);

  const returnToCurrentPosition = useCallback(() => {
    setAutoFollow(true);
  }, []);

  const navigateMatch = useCallback(
    (direction: 1 | -1) => {
      if (matches.length === 0) return;
      const next =
        (activeMatchIndex + direction + matches.length) % matches.length;
      setActiveMatchIndex(next);
      const match = matches[next];
      onSeek(segments[match.segmentIndex].t_start);
      const el = segmentRefs.current.get(match.segmentIndex);
      if (el) {
        if (scrollTimerRef.current) clearTimeout(scrollTimerRef.current);
        programmaticScroll.current = true;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        scrollTimerRef.current = setTimeout(() => {
          programmaticScroll.current = false;
          scrollTimerRef.current = null;
        }, 300);
      }
    },
    [matches, activeMatchIndex, segments, onSeek],
  );

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchQuery(e.target.value);
      if (e.target.value !== prevQueryRef.current) {
        setActiveMatchIndex(0);
        prevQueryRef.current = e.target.value;
      }
    },
    [],
  );

  const handleSearchKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        navigateMatch(e.shiftKey ? -1 : 1);
      } else if (e.key === 'Escape') {
        setSearchOpen(false);
        setSearchQuery('');
      }
    },
    [navigateMatch],
  );

  if (segments.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-brand-silver">
        No transcript available for this recording.
      </p>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Redaction notice */}
      {hasRedactions && (
        <div className="mb-2 flex items-center gap-2 rounded border border-yellow-500/20 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-300">
          <Shield className="h-3.5 w-3.5 shrink-0" />
          Transcript has been processed for privacy. Personal information
          appears as placeholders.
        </div>
      )}

      {/* Search bar */}
      <div className="mb-2 flex items-center gap-2">
        <button
          type="button"
          onClick={() => setSearchOpen(!searchOpen)}
          className="rounded p-1 text-brand-silver hover:text-white"
          aria-label="Toggle search"
        >
          <Search className="h-4 w-4" />
        </button>
        {searchOpen && (
          <div className="flex flex-1 items-center gap-1.5">
            <input
              type="text"
              value={searchQuery}
              onChange={handleSearchChange}
              onKeyDown={handleSearchKeyDown}
              placeholder="Search transcript..."
              className="flex-1 rounded border border-white/10 bg-white/5 px-2 py-1 text-xs text-white placeholder:text-brand-silver/50 focus:border-brand-electric/50 focus:outline-none"
              autoFocus
              data-testid="transcript-search-input"
            />
            {matches.length > 0 && (
              <span className="shrink-0 text-xs tabular-nums text-brand-silver" data-testid="search-match-count">
                {activeMatchIndex + 1}/{matches.length}
              </span>
            )}
            {matches.length === 0 && searchQuery && (
              <span className="shrink-0 text-xs text-brand-silver" data-testid="search-match-count">
                0 matches
              </span>
            )}
            <button
              type="button"
              onClick={() => navigateMatch(-1)}
              disabled={matches.length === 0}
              className="rounded p-0.5 text-brand-silver hover:text-white disabled:opacity-30"
              aria-label="Previous match"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => navigateMatch(1)}
              disabled={matches.length === 0}
              className="rounded p-0.5 text-brand-silver hover:text-white disabled:opacity-30"
              aria-label="Next match"
            >
              <ArrowDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Transcript segments */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
        role="list"
        aria-label="Transcript"
      >
        {segments.map((seg, i) => {
          const isCurrent = i === currentSegmentIndex;
          return (
            <div
              key={`${i}-${seg.t_start}-${seg.t_end}`}
              ref={(el) => {
                if (el) segmentRefs.current.set(i, el);
                else segmentRefs.current.delete(i);
              }}
              role="listitem"
              data-testid="transcript-segment"
              className={`flex gap-2 border-l-2 px-2 py-1.5 transition-colors ${
                isCurrent
                  ? 'border-brand-electric bg-brand-electric/10'
                  : 'border-transparent hover:bg-white/5'
              }`}
              style={{
                contentVisibility: 'auto',
                containIntrinsicSize: '0 3.5rem',
              }}
            >
              {/* Timestamp — clickable */}
              <button
                type="button"
                onClick={() => onSeek(seg.t_start)}
                className="shrink-0 pt-0.5 text-xs tabular-nums text-brand-silver/70 hover:text-brand-electric"
                data-testid="segment-timestamp"
              >
                {formatTime(seg.t_start)}
              </button>

              <div className="min-w-0 flex-1">
                {/* Speaker label */}
                <span
                  className={`text-xs font-medium ${speakerColor(seg.speaker)}`}
                  data-testid="speaker-label"
                  data-speaker={seg.speaker}
                >
                  {speakerLabel(seg.speaker)}
                </span>

                {/* Text */}
                <p className="mt-0.5 text-sm leading-relaxed text-white/90">
                  {searchQuery
                    ? highlightText(
                        seg.text,
                        matches,
                        i,
                        activeMatchIndex,
                        matches,
                      )
                    : seg.text}
                  {seg.redaction_applied && (
                    <Shield className="ml-1 inline h-3 w-3 text-yellow-400/60" />
                  )}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Return to current position */}
      {!autoFollow && currentSegmentIndex >= 0 && (
        <button
          type="button"
          onClick={returnToCurrentPosition}
          className="mt-1 flex w-full items-center justify-center gap-1 rounded bg-brand-electric/20 py-1.5 text-xs text-brand-electric hover:bg-brand-electric/30"
          data-testid="return-to-current"
        >
          <ChevronDown className="h-3.5 w-3.5" />
          Return to current position
        </button>
      )}
    </div>
  );
}
