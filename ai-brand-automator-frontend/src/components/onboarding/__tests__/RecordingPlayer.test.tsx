/**
 * I-02 · RecordingPlayer with key-moment seeking.
 *
 * Tests summary rendering, key moment chips, and audio controls.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import RecordingPlayer from '@/components/onboarding/RecordingPlayer';
import type { RecordingDetail } from '@/lib/onboarding-sessions';

function detail(overrides: Partial<RecordingDetail> = {}): RecordingDetail {
  return {
    id: 'rec-1',
    session: 'sess-1',
    modality: 'AUDIO',
    status: 'SUMMARIZED',
    duration_s: 120,
    audio_asset: 'asset-1',
    has_transcript: false,
    has_summary: true,
    started_at: '2026-08-15T10:00:00Z',
    stopped_at: '2026-08-15T10:02:00Z',
    summary: {
      text: 'The meeting covered brand positioning.\n\nKey decisions were made about target audience.',
      key_moments: [
        { t: 5.0, label: 'introduction' },
        { t: 45.0, label: 'brand vision' },
        { t: 90.0, label: 'budget discussion' },
      ],
    },
    playback_url: 'https://storage.example.com/audio.webm',
    ...overrides,
  };
}

jest.mock('@/lib/onboarding-sessions', () => ({
  getRecordingDetail: jest.fn(),
}));

const mockGetDetail = jest.requireMock('@/lib/onboarding-sessions')
  .getRecordingDetail as jest.Mock;

beforeEach(() => {
  mockGetDetail.mockReset();
});

it('shows loading state initially', () => {
  mockGetDetail.mockReturnValue(new Promise(() => {}));
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  expect(document.querySelector('.animate-spin')).toBeTruthy();
});

it('renders summary text after loading', async () => {
  mockGetDetail.mockResolvedValue(detail());
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  await waitFor(() => {
    expect(screen.getByText(/brand positioning/)).toBeInTheDocument();
    expect(screen.getByText(/target audience/)).toBeInTheDocument();
  });
});

it('renders key moment chips', async () => {
  mockGetDetail.mockResolvedValue(detail());
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  await waitFor(() => {
    expect(screen.getByText('introduction')).toBeInTheDocument();
    expect(screen.getByText('brand vision')).toBeInTheDocument();
    expect(screen.getByText('budget discussion')).toBeInTheDocument();
  });
});

it('renders formatted timestamps on key moment chips', async () => {
  mockGetDetail.mockResolvedValue(detail());
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  await waitFor(() => {
    expect(screen.getByText('0:05')).toBeInTheDocument();
    expect(screen.getByText('0:45')).toBeInTheDocument();
    expect(screen.getByText('1:30')).toBeInTheDocument();
  });
});

it('calls onClose when back button is clicked', async () => {
  mockGetDetail.mockResolvedValue(detail());
  const onClose = jest.fn();
  render(<RecordingPlayer recordingId="rec-1" onClose={onClose} />);
  await waitFor(() => screen.getByText('Recording'));
  fireEvent.click(screen.getByText('Recording'));
  expect(onClose).toHaveBeenCalled();
});

it('calls onClose when X button is clicked', async () => {
  mockGetDetail.mockResolvedValue(detail());
  const onClose = jest.fn();
  render(<RecordingPlayer recordingId="rec-1" onClose={onClose} />);
  await waitFor(() => screen.getByLabelText('Close player'));
  fireEvent.click(screen.getByLabelText('Close player'));
  expect(onClose).toHaveBeenCalled();
});

it('shows error state when fetch fails', async () => {
  mockGetDetail.mockRejectedValue(new Error('Network error'));
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  await waitFor(() => {
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });
});

it('renders play button when playback url exists', async () => {
  mockGetDetail.mockResolvedValue(detail());
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  await waitFor(() => {
    expect(screen.getByLabelText('Play')).toBeInTheDocument();
  });
});

it('handles recording without summary', async () => {
  mockGetDetail.mockResolvedValue(detail({ summary: null, playback_url: undefined }));
  render(<RecordingPlayer recordingId="rec-1" onClose={jest.fn()} />);
  await waitFor(() => {
    expect(screen.getByText(/No summary or playback/)).toBeInTheDocument();
  });
});
