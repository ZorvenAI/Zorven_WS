/**
 * O-06 · LegalTranscriptHeader tests.
 *
 * AC-1: Date and time are auto-captured.
 * AC-2: Attendee list populated from roll call.
 * AC-3: Consent details pulled from ConsentRecord.
 * AC-5: No field requires manual entry.
 */

import { render, screen } from '@testing-library/react';
import LegalTranscriptHeader from '@/components/onboarding/LegalTranscriptHeader';
import type { TranscriptHeader } from '@/lib/onboarding-sessions';

function makeHeader(overrides: Partial<TranscriptHeader> = {}): TranscriptHeader {
  return {
    date: '2026-09-12',
    time_utc: '14:30 UTC',
    started_at_iso: '2026-09-12T14:30:00Z',
    stopped_at_iso: '2026-09-12T15:30:00Z',
    session_id: '6',
    session_company: 'Pomodoro Pizza',
    attendees: [
      {
        name: 'John Smith',
        role: 'operator',
        mic_label: 'Built-in Mic',
        stream_index: 0,
        checked_in_at: '2026-09-12T14:30:05Z',
      },
      {
        name: 'Mario Rossi',
        role: 'participant',
        mic_label: 'USB Mic',
        stream_index: 1,
        checked_in_at: '2026-09-12T14:30:12Z',
      },
    ],
    consent: {
      subject_name: 'Pomodoro Owner',
      method: 'CHECKBOX',
      granted_at: '2026-09-09T10:15:00Z',
      scope: { audio: true, transcript: true },
    },
    ...overrides,
  };
}

describe('O-06 · LegalTranscriptHeader', () => {
  it('AC-1: renders date and time', () => {
    render(<LegalTranscriptHeader header={makeHeader()} />);
    expect(screen.getByTestId('legal-transcript-header')).toBeInTheDocument();
    expect(screen.getByText(/September 12, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/14:30 UTC/)).toBeInTheDocument();
  });

  it('AC-1: renders company name', () => {
    render(<LegalTranscriptHeader header={makeHeader()} />);
    expect(screen.getByText(/Pomodoro Pizza/)).toBeInTheDocument();
  });

  it('AC-2: renders attendees from roll call', () => {
    render(<LegalTranscriptHeader header={makeHeader()} />);
    expect(screen.getByText('John Smith')).toBeInTheDocument();
    expect(screen.getByText('Mario Rossi')).toBeInTheDocument();
    expect(screen.getByText('(operator)')).toBeInTheDocument();
    expect(screen.getByText('(participant)')).toBeInTheDocument();
  });

  it('AC-3: renders consent details', () => {
    render(<LegalTranscriptHeader header={makeHeader()} />);
    expect(screen.getByText(/Pomodoro Owner/)).toBeInTheDocument();
    expect(screen.getByText(/Checkbox/)).toBeInTheDocument();
  });

  it('returns null when all data is empty', () => {
    const empty: TranscriptHeader = {
      date: null,
      time_utc: null,
      started_at_iso: null,
      stopped_at_iso: null,
      session_id: '1',
      session_company: null,
      attendees: [],
      consent: null,
    };
    const { container } = render(<LegalTranscriptHeader header={empty} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders without consent when absent', () => {
    render(<LegalTranscriptHeader header={makeHeader({ consent: null })} />);
    expect(screen.getByText('John Smith')).toBeInTheDocument();
    expect(screen.queryByText(/Consent/)).not.toBeInTheDocument();
  });

  it('renders without attendees when empty', () => {
    render(<LegalTranscriptHeader header={makeHeader({ attendees: [] })} />);
    expect(screen.queryByText(/Attendees/)).not.toBeInTheDocument();
    expect(screen.getByText(/Pomodoro Owner/)).toBeInTheDocument();
  });
});
