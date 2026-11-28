'use client';

/**
 * How long a kept erasure request holds its signed records (decision D7).
 *
 * Only sets the default hold-until date offered when a request is kept;
 * existing holds keep the date they were given.
 */

import { useEffect, useState } from 'react';
import { FileLock2, Loader2 } from 'lucide-react';

import { getLegalHoldYears, setLegalHoldYears } from '@/lib/erasure-review';

const MIN_YEARS = 1;
const MAX_YEARS = 25;

export default function LegalHoldSettings() {
  const [saved, setSaved] = useState<number | null>(null);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLegalHoldYears()
      .then((years) => {
        if (cancelled) return;
        setSaved(years);
        setValue(String(years));
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Could not load.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const years = Number(value);
  const valid = Number.isInteger(years) && years >= MIN_YEARS && years <= MAX_YEARS;

  const save = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const stored = await setLegalHoldYears(years);
      setSaved(stored);
      setValue(String(stored));
      setMessage('Saved. New legal holds default to this period.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not save.');
    } finally {
      setBusy(false);
    }
  };

  if (saved === null && !error) {
    return (
      <div className="glass-card flex items-center gap-2 p-6 text-brand-silver">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading legal hold period…
      </div>
    );
  }

  return (
    <div className="glass-card space-y-3 p-6">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
        <FileLock2 className="h-4 w-4 text-brand-electric" aria-hidden />
        Legal hold period
      </h3>
      <p className="text-xs text-brand-silver">
        When you keep a request because of signed records, the hold lasts this long by
        default. You can still pick a different date for each request.
      </p>
      <div className="flex items-center gap-2">
        <label htmlFor="legal-hold-years" className="text-sm text-brand-silver">
          Keep for
        </label>
        <input
          id="legal-hold-years"
          type="number"
          min={MIN_YEARS}
          max={MAX_YEARS}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="w-20 rounded border border-white/15 bg-transparent px-3 py-2 text-sm text-white"
        />
        <span className="text-sm text-brand-silver">years</span>
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || !valid || years === saved}
          className="btn-primary px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-40"
        >
          Save
        </button>
      </div>
      {!valid && value !== '' && (
        <p className="text-xs text-rose-300">
          Enter a whole number from {MIN_YEARS} to {MAX_YEARS}.
        </p>
      )}
      {message && (
        <p role="status" className="text-xs text-emerald-300">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
        </p>
      )}
    </div>
  );
}
