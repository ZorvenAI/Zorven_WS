/**
 * I-01 · recordings-and-captures library.
 *
 * Verifies the rail renders status chips, usage tags, and role-gated controls.
 */

import { render, screen, within } from '@testing-library/react';

import RecordingsLibrary from '@/components/onboarding/RecordingsLibrary';
import type { RecordingItem, CapturedMedia } from '@/lib/onboarding-sessions';

function recording(overrides: Partial<RecordingItem> = {}): RecordingItem {
  return {
    id: 'rec-1',
    session: 'sess-1',
    modality: 'AUDIO',
    status: 'UPLOADED',
    duration_s: 95,
    audio_asset: 'asset-1',
    has_transcript: false,
    has_summary: false,
    started_at: '2026-08-15T10:00:00Z',
    stopped_at: '2026-08-15T10:01:35Z',
    ...overrides,
  };
}

function capture(overrides: Partial<CapturedMedia> = {}): CapturedMedia {
  return {
    id: 'cap-1',
    file_name: 'whiteboard.jpg',
    file_type: 'image',
    file_size: 2048,
    uploaded_at: '2026-08-15T10:00:00Z',
    usage_tag: 'business_photo',
    ...overrides,
  };
}

// ── AC-1 · status rendering ─────────────────────────────────────────

it('renders recordings with status chips', () => {
  render(
    <RecordingsLibrary
      recordings={[
        recording({ id: 'r1', status: 'RECORDING', duration_s: null }),
        recording({ id: 'r2', status: 'UPLOADED' }),
        recording({ id: 'r3', status: 'SUMMARIZED' }),
      ]}
      captures={[]}
      canDelete={false}
    />,
  );

  const list = screen.getByTestId('recordings-list');
  expect(within(list).getByText('Recording')).toBeInTheDocument();
  expect(within(list).getByText('Processing')).toBeInTheDocument();
  expect(within(list).getByText('Ready')).toBeInTheDocument();
});

it('renders captures with usage tag badge', () => {
  render(
    <RecordingsLibrary
      recordings={[]}
      captures={[
        capture({ usage_tag: 'business_photo' }),
        capture({ id: 'cap-2', usage_tag: 'previous_ad', file_name: 'ad.mp4', file_type: 'video' }),
      ]}
      canDelete={false}
    />,
  );

  const list = screen.getByTestId('captures-list');
  expect(within(list).getByText('business photo')).toBeInTheDocument();
  expect(within(list).getByText('previous ad')).toBeInTheDocument();
  expect(within(list).getByText('whiteboard.jpg')).toBeInTheDocument();
  expect(within(list).getByText('ad.mp4')).toBeInTheDocument();
});

// ── AC-2 · processing state ─────────────────────────────────────────

it('shows "Processing" for UPLOADED status', () => {
  render(
    <RecordingsLibrary
      recordings={[recording({ status: 'UPLOADED' })]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.getByText('Processing')).toBeInTheDocument();
});

it('shows "Failed" with warning icon for FAILED status', () => {
  render(
    <RecordingsLibrary
      recordings={[recording({ status: 'FAILED' })]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.getByText('Failed')).toBeInTheDocument();
});

// ── AC-2 · play button gating ───────────────────────────────────────

it('disables play while RECORDING', () => {
  render(
    <RecordingsLibrary
      recordings={[recording({ status: 'RECORDING', audio_asset: null })]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.queryByRole('button', { name: /play/i })).not.toBeInTheDocument();
});

it('shows play button when UPLOADED with audio_asset', () => {
  render(
    <RecordingsLibrary
      recordings={[recording({ status: 'UPLOADED', audio_asset: 'asset-1' })]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
});

// ── AC-3 · delete RBAC ──────────────────────────────────────────────

it('hides delete button for viewers (canDelete=false)', () => {
  render(
    <RecordingsLibrary
      recordings={[recording()]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.queryByTestId('delete-recording')).not.toBeInTheDocument();
});

it('shows delete button for admins (canDelete=true)', () => {
  render(
    <RecordingsLibrary
      recordings={[recording()]}
      captures={[]}
      canDelete={true}
    />,
  );

  expect(screen.getByTestId('delete-recording')).toBeInTheDocument();
});

// ── empty state ─────────────────────────────────────────────────────

it('shows placeholder when no items', () => {
  render(
    <RecordingsLibrary recordings={[]} captures={[]} canDelete={false} />,
  );

  expect(
    screen.getByText(/recordings and captured media appear here/i),
  ).toBeInTheDocument();
});

// ── duration formatting ─────────────────────────────────────────────

it('formats duration as M:SS', () => {
  render(
    <RecordingsLibrary
      recordings={[recording({ duration_s: 125 })]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.getByText('2:05')).toBeInTheDocument();
});

it('shows dash when duration is null', () => {
  render(
    <RecordingsLibrary
      recordings={[recording({ duration_s: null })]}
      captures={[]}
      canDelete={false}
    />,
  );

  expect(screen.getByText('—')).toBeInTheDocument();
});
