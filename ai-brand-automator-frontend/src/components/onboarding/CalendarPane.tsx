'use client';

/**
 * CalendarPane — onboarding meetings, month or week (D-01, Design §11).
 *
 * Replaces the placeholder E-01 left. Deliberately not a general-purpose
 * calendar: the card warns that "scope creep here is unbounded", so this shows
 * onboarding meetings, in two views, and nothing else. No library, for the
 * same reason — a calendar package brings its own 90% and an invitation to
 * use it.
 *
 * Everything renders in the *viewer's* zone. The server stores a UTC instant
 * plus the IANA zone it was booked in; this formats the instant locally and
 * shows the booking zone alongside when they differ, because "09:00 in
 * Europe/London" is what the operator agreed with the brand owner and a
 * colleague in Sydney needs both halves.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';

import { useTenantRole } from '@/hooks/useTenantRole';
import {
  cancelMeeting,
  createMeeting,
  listMeetings,
  listSessions,
  viewerTimezone,
  type OnboardingSessionSummary,
  type ScheduledMeeting,
} from '@/lib/onboarding-sessions';

type View = 'month' | 'week';

function startOfDay(date: Date): Date {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

/** Monday-first, which is what the rest of the product assumes. */
function startOfWeek(date: Date): Date {
  const copy = startOfDay(date);
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  return copy;
}

function startOfMonthGrid(date: Date): Date {
  return startOfWeek(new Date(date.getFullYear(), date.getMonth(), 1));
}

function addDays(date: Date, days: number): Date {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

/**
 * The window a view covers.
 *
 * Computed in local time and sent as UTC instants, which is the only
 * conversion in this component — the server does the filtering, so a week
 * boundary that lands mid-afternoon UTC still selects the right meetings.
 */
function windowFor(view: View, anchor: Date): { from: Date; to: Date; days: Date[] } {
  const from = view === 'month' ? startOfMonthGrid(anchor) : startOfWeek(anchor);
  const length = view === 'month' ? 42 : 7;
  const days = Array.from({ length }, (_, index) => addDays(from, index));
  return { from, to: addDays(from, length), days };
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export interface CalendarPaneProps {
  /** Fixed "today" for tests; the component is otherwise clock-dependent. */
  now?: Date;
}

export default function CalendarPane({ now }: CalendarPaneProps) {
  const { canEdit: canEditRole } = useTenantRole();
  // Hydration guard, per the project rule and E-01's review: useTenantRole
  // reads a localStorage-backed context, so the server and first client
  // renders otherwise disagree.
  const [hasMounted, setHasMounted] = useState(false);
  useEffect(() => setHasMounted(true), []);
  const canEdit = hasMounted && canEditRole;

  const today = useMemo(() => now ?? new Date(), [now]);
  const [view, setView] = useState<View>('month');
  const [anchor, setAnchor] = useState<Date>(() => startOfDay(now ?? new Date()));
  const [meetings, setMeetings] = useState<ScheduledMeeting[]>([]);
  const [sessions, setSessions] = useState<OnboardingSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { from, to, days } = useMemo(() => windowFor(view, anchor), [view, anchor]);
  const zone = useMemo(() => viewerTimezone(), []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setMeetings(await listMeetings(from, to));
    } catch (error) {
      // Cleared, not stale: a calendar showing last month's meetings as if
      // they were this month's is worse than one showing none.
      setMeetings([]);
      console.error('Failed to load meetings:', error);
    } finally {
      setLoading(false);
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    // A meeting belongs to a session, so the form needs the list. Loaded once
    // rather than per window change — the sessions do not move when the
    // operator pages to next month.
    listSessions()
      .then(setSessions)
      .catch((problem) => console.error('Failed to load sessions:', problem));
  }, []);

  async function onSchedule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const starts = String(form.get('starts') || '');
    const minutes = Number(form.get('minutes') || 60);
    if (!starts) return;

    // datetime-local gives a *local* wall-clock string with no zone. Reading
    // it through Date interprets it in the browser's zone, which is exactly
    // what the operator meant, and toISOString then hands the server the UTC
    // instant. The zone name travels separately so the booking's own zone
    // survives a DST change (D-01 AC-2).
    const startsAt = new Date(starts);
    const endsAt = new Date(startsAt.getTime() + minutes * 60_000);

    setSaving(true);
    setError(null);
    try {
      await createMeeting({
        session: String(form.get('session')),
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
        timezone: zone,
      });
      await load();
      event.currentTarget.reset();
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not schedule.');
    } finally {
      setSaving(false);
    }
  }

  const byDay = useMemo(() => {
    const map = new Map<string, ScheduledMeeting[]>();
    for (const meeting of meetings) {
      if (meeting.status === 'CANCELLED') continue;
      // Grouped by the *viewer's* local day. A meeting at 23:00 UTC belongs to
      // tomorrow for someone in Sydney, and putting it on the UTC day would
      // show it on the wrong square.
      const local = new Date(meeting.starts_at);
      const key = startOfDay(local).toDateString();
      map.set(key, [...(map.get(key) ?? []), meeting]);
    }
    return map;
  }, [meetings]);

  const shift = (direction: 1 | -1) =>
    setAnchor((current) =>
      view === 'month'
        ? new Date(current.getFullYear(), current.getMonth() + direction, 1)
        : addDays(current, direction * 7),
    );

  async function onCancel(meeting: ScheduledMeeting) {
    try {
      await cancelMeeting(meeting.id);
      await load();
    } catch (error) {
      console.error('Failed to cancel the meeting:', error);
    }
  }

  return (
    <section aria-labelledby="calendar-heading" className="glass-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-brand-electric" aria-hidden />
          <h2 id="calendar-heading" className="text-sm font-semibold text-white">
            {anchor.toLocaleString(undefined, { month: 'long', year: 'numeric' })}
          </h2>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-white/10 p-0.5" role="group" aria-label="Calendar view">
            {(['month', 'week'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setView(option)}
                aria-pressed={view === option}
                className={`rounded px-2 py-1 text-xs capitalize ${
                  view === option ? 'bg-white/10 text-white' : 'text-brand-silver'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => shift(-1)}
            aria-label="Previous"
            className="rounded p-1 text-brand-silver hover:bg-white/5"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden />
          </button>
          <button
            type="button"
            onClick={() => shift(1)}
            aria-label="Next"
            className="rounded p-1 text-brand-silver hover:bg-white/5"
          >
            <ChevronRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>

      <p className="mt-2 text-xs text-brand-silver">
        Times shown in {zone}
      </p>

      {loading ? (
        <p className="mt-3 text-sm text-brand-silver">Loading meetings…</p>
      ) : (
        <div
          className={`mt-3 grid gap-1 ${view === 'month' ? 'grid-cols-7' : 'grid-cols-7'}`}
          role="grid"
          aria-label={`Onboarding meetings, ${view} view`}
        >
          {days.map((day) => {
            const dayMeetings = byDay.get(day.toDateString()) ?? [];
            const outside = view === 'month' && day.getMonth() !== anchor.getMonth();
            return (
              <div
                key={day.toISOString()}
                role="gridcell"
                aria-label={day.toDateString()}
                className={`min-h-16 rounded border border-white/5 p-1 ${
                  outside ? 'opacity-40' : ''
                } ${sameDay(day, today) ? 'ring-1 ring-brand-electric/40' : ''}`}
              >
                <span className="text-[10px] text-brand-silver">{day.getDate()}</span>
                {dayMeetings.map((meeting) => (
                  <div key={meeting.id} className="mt-1 rounded bg-brand-electric/15 p-1">
                    <p className="truncate text-[11px] text-white">
                      {new Date(meeting.starts_at).toLocaleTimeString(undefined, {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}{' '}
                      {meeting.title || 'Onboarding meeting'}
                    </p>
                    {meeting.timezone !== zone && (
                      // Both halves. The operator agreed a local time with the
                      // brand owner; a colleague elsewhere needs to know which.
                      <p className="truncate text-[10px] text-brand-silver">
                        booked {meeting.timezone}
                      </p>
                    )}
                    {canEdit && (
                      <button
                        type="button"
                        onClick={() => onCancel(meeting)}
                        className="mt-0.5 text-[10px] text-rose-300 hover:underline"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      )}

      {/*
        AC-3: a Viewer gets a read-only calendar. Absent, not disabled — the
        precedent E-01 set, and for the same reason: a greyed button with a
        live endpoint behind it is not read-only.

        AC-1 requires creation to work, so this is a real form rather than a
        button that opens nothing. An affordance that does not do what it says
        is worse than one that is missing.
      */}
      {canEdit && (
        <form onSubmit={onSchedule} className="mt-4 flex flex-wrap items-end gap-2">
          <label className="text-xs text-brand-silver">
            Session
            <select
              name="session"
              required
              className="mt-1 block rounded border border-white/10 bg-transparent px-2 py-1 text-sm text-white"
            >
              {sessions.map((session) => (
                <option key={session.id} value={session.id} className="bg-brand-midnight">
                  {session.company ?? 'Unassigned'}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-brand-silver">
            Starts
            <input
              type="datetime-local"
              name="starts"
              required
              className="mt-1 block rounded border border-white/10 bg-transparent px-2 py-1 text-sm text-white"
            />
          </label>
          <label className="text-xs text-brand-silver">
            Minutes
            <input
              type="number"
              name="minutes"
              defaultValue={60}
              min={5}
              step={5}
              className="mt-1 block w-20 rounded border border-white/10 bg-transparent px-2 py-1 text-sm text-white"
            />
          </label>
          <button type="submit" className="btn-primary text-sm" disabled={saving}>
            {saving ? 'Scheduling…' : 'Schedule a meeting'}
          </button>
          {error && (
            <p role="alert" className="w-full text-xs text-rose-300">
              {error}
            </p>
          )}
        </form>
      )}
    </section>
  );
}
