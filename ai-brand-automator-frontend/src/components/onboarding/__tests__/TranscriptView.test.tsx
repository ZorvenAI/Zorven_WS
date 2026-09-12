/**
 * I-03 · TranscriptView — speaker-attributed, synced, searchable transcript.
 */

import { render, screen, fireEvent, act } from '@testing-library/react';

import TranscriptView from '@/components/onboarding/TranscriptView';
import type { TranscriptSegment } from '@/lib/onboarding-sessions';

beforeAll(() => {
  Element.prototype.scrollIntoView = jest.fn();
});

function seg(overrides: Partial<TranscriptSegment> = {}): TranscriptSegment {
  return {
    text: 'Hello there.',
    speaker: 0,
    t_start: 0.0,
    t_end: 2.0,
    redaction_applied: false,
    ...overrides,
  };
}

const SEGMENTS: TranscriptSegment[] = [
  seg({ text: 'Welcome to the meeting.', speaker: 0, t_start: 0.0, t_end: 3.0 }),
  seg({ text: 'Thanks for having me.', speaker: 1, t_start: 3.5, t_end: 5.5 }),
  seg({
    text: 'My number is [PHONE_NUMBER].',
    speaker: 1,
    t_start: 6.0,
    t_end: 8.0,
    redaction_applied: true,
  }),
  seg({ text: 'Let us discuss the brand.', speaker: 0, t_start: 9.0, t_end: 12.0 }),
  seg({ text: 'Our brand vision is global.', speaker: 1, t_start: 13.0, t_end: 16.0 }),
];

it('renders speaker labels and timestamps (AC-1)', () => {
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={jest.fn()}
    />,
  );
  const labels = screen.getAllByTestId('speaker-label');
  expect(labels.length).toBe(SEGMENTS.length);
  expect(labels[0]).toHaveTextContent('Speaker 1');
  expect(labels[1]).toHaveTextContent('Speaker 2');

  const timestamps = screen.getAllByTestId('segment-timestamp');
  expect(timestamps[0]).toHaveTextContent('0:00');
  expect(timestamps[1]).toHaveTextContent('0:03');
});

it('speakers are visually distinguished (AC-1)', () => {
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={jest.fn()}
    />,
  );
  const labels = screen.getAllByTestId('speaker-label');
  const speaker0Class = labels[0].className;
  const speaker1Class = labels[1].className;
  expect(speaker0Class).not.toBe(speaker1Class);
});

it('highlights the current segment (AC-2)', () => {
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={4.0}
      onSeek={jest.fn()}
    />,
  );
  const items = screen.getAllByTestId('transcript-segment');
  expect(items[1].className).toContain('border-brand-electric');
  expect(items[0].className).not.toContain('border-brand-electric');
});

it('clicking a segment timestamp seeks the player (AC-2)', () => {
  const onSeek = jest.fn();
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={onSeek}
    />,
  );
  const timestamps = screen.getAllByTestId('segment-timestamp');
  fireEvent.click(timestamps[2]);
  expect(onSeek).toHaveBeenCalledWith(6.0);
});

it('shows "Return to current position" after manual scroll (AC-2)', () => {
  jest.useFakeTimers();
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={4.0}
      onSeek={jest.fn()}
    />,
  );
  // Advance past the 300ms programmatic-scroll guard set by auto-follow
  act(() => jest.advanceTimersByTime(350));
  const list = screen.getByRole('list');
  fireEvent.scroll(list);
  expect(screen.getByTestId('return-to-current')).toBeInTheDocument();
  jest.useRealTimers();
});

it('search finds and counts matches (AC-3)', () => {
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={jest.fn()}
    />,
  );
  fireEvent.click(screen.getByLabelText('Toggle search'));
  const input = screen.getByTestId('transcript-search-input');
  fireEvent.change(input, { target: { value: 'brand' } });

  const count = screen.getByTestId('search-match-count');
  expect(count).toHaveTextContent('1/2');
});

it('search navigation seeks the player (AC-3)', () => {
  const onSeek = jest.fn();
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={onSeek}
    />,
  );
  fireEvent.click(screen.getByLabelText('Toggle search'));
  const input = screen.getByTestId('transcript-search-input');
  fireEvent.change(input, { target: { value: 'brand' } });

  fireEvent.click(screen.getByLabelText('Next match'));
  expect(onSeek).toHaveBeenCalledWith(13.0);
});

it('redacted segments show placeholder and shield icon (AC-4)', () => {
  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={jest.fn()}
    />,
  );
  expect(screen.getByText(/\[PHONE_NUMBER\]/)).toBeInTheDocument();
  expect(
    screen.getByText(/Transcript has been processed for privacy/),
  ).toBeInTheDocument();
});

it('shows empty state when no segments', () => {
  render(
    <TranscriptView
      segments={[]}
      currentTime={0}
      onSeek={jest.fn()}
    />,
  );
  expect(screen.getByText(/No transcript available/)).toBeInTheDocument();
});

it('deep link scrolls to segment at initialTime', () => {
  const scrollSpy = Element.prototype.scrollIntoView as jest.Mock;
  scrollSpy.mockClear();

  render(
    <TranscriptView
      segments={SEGMENTS}
      currentTime={0}
      onSeek={jest.fn()}
      initialTime={7.0}
    />,
  );
  expect(scrollSpy).toHaveBeenCalled();
});
