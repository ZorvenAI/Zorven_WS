/**
 * H-02 · SnippetControl — short video snippet capture with usage tagging.
 *
 * jsdom has no getUserMedia or MediaRecorder, so both are mocked. The tests
 * verify the state machine, consent gate, tagging, and onCapture callback.
 */

import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import SnippetControl from '@/components/onboarding/SnippetControl';
import { USAGE_TAGS } from '@/components/onboarding/CaptureControl';

const fakeStop = jest.fn();
const fakeStream = {
  getTracks: () => [{ stop: fakeStop }],
  getAudioTracks: () => [],
  getVideoTracks: () => [{ stop: fakeStop, readyState: 'live' }],
};

let mockRecorderInstance: {
  start: jest.Mock;
  stop: jest.Mock;
  state: string;
  ondataavailable: ((e: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
};

beforeEach(() => {
  jest.useFakeTimers();
  fakeStop.mockClear();

  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: jest.fn().mockResolvedValue(fakeStream),
    },
    writable: true,
    configurable: true,
  });

  mockRecorderInstance = {
    start: jest.fn(),
    stop: jest.fn(function (this: typeof mockRecorderInstance) {
      this.state = 'inactive';
      if (this.ondataavailable) {
        this.ondataavailable({ data: new Blob(['video-data'], { type: 'video/webm' }) });
      }
      if (this.onstop) {
        this.onstop();
      }
    }),
    state: 'inactive',
    ondataavailable: null,
    onstop: null,
  };

  const MockMediaRecorder = Object.assign(
    jest.fn().mockImplementation(() => {
      mockRecorderInstance.state = 'recording';
      return mockRecorderInstance;
    }),
    { isTypeSupported: jest.fn(() => true) },
  );

  Object.defineProperty(global, 'MediaRecorder', {
    value: MockMediaRecorder,
    writable: true,
    configurable: true,
  });

  global.URL.createObjectURL = jest.fn(() => 'blob:fake-url');
  global.URL.revokeObjectURL = jest.fn();
});

afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

// ── AC-1 · consent gate ─────────────────────────────────────────────

it('consent gates snippet — shows aria-disabled without consent', () => {
  render(<SnippetControl consentGranted={false} />);
  const btn = screen.getByRole('button', { name: /capture video/i });
  expect(btn).toHaveAttribute('aria-disabled', 'true');
});

it('consent-gated button calls onRecordConsent on click', async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  const onConsent = jest.fn();
  render(<SnippetControl consentGranted={false} onRecordConsent={onConsent} />);
  await user.click(screen.getByRole('button', { name: /capture video/i }));
  expect(onConsent).toHaveBeenCalledTimes(1);
});

it('shows a live capture button when consent is granted', () => {
  render(<SnippetControl consentGranted={true} />);
  const btn = screen.getByRole('button', { name: /capture video/i });
  expect(btn).not.toHaveAttribute('aria-disabled');
  expect(btn).not.toBeDisabled();
});

// ── Recording overlay ───────────────────────────────────────────────

it('opens recording overlay on click', async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  render(<SnippetControl consentGranted={true} />);

  await user.click(screen.getByRole('button', { name: /capture video/i }));

  expect(await screen.findByTestId('snippet-overlay')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

it('auto-stops at max seconds and moves to confirm', async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  render(<SnippetControl consentGranted={true} />);

  await user.click(screen.getByRole('button', { name: /capture video/i }));

  await screen.findByTestId('snippet-overlay');

  act(() => {
    jest.advanceTimersByTime(30000);
  });

  expect(screen.getByTestId('snippet-playback')).toBeInTheDocument();
});

it('countdown appears at 10s remaining', async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  render(<SnippetControl consentGranted={true} />);

  await user.click(screen.getByRole('button', { name: /capture video/i }));
  await screen.findByTestId('snippet-overlay');

  // No countdown before 20s
  expect(screen.queryByTestId('countdown-overlay')).not.toBeInTheDocument();

  act(() => {
    jest.advanceTimersByTime(20200);
  });

  expect(screen.getByTestId('countdown-overlay')).toBeInTheDocument();
});

it('dismiss returns to idle', async () => {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  render(<SnippetControl consentGranted={true} />);

  await user.click(screen.getByRole('button', { name: /capture video/i }));
  await screen.findByTestId('snippet-overlay');

  await user.click(screen.getByRole('button', { name: /close/i }));

  expect(screen.queryByTestId('snippet-overlay')).not.toBeInTheDocument();
});

// ── Tagging phase ───────────────────────────────────────────────────

async function reachTaggingPhase(onCapture?: jest.Mock) {
  const user = userEvent.setup({ advanceTimers: jest.advanceTimersByTime });
  render(<SnippetControl consentGranted={true} onCapture={onCapture} />);

  // Start recording
  await user.click(screen.getByRole('button', { name: /capture video/i }));
  await screen.findByTestId('snippet-overlay');

  // Stop recording
  await user.click(screen.getByRole('button', { name: /stop recording/i }));

  // Confirm video
  await screen.findByTestId('snippet-playback');
  await user.click(screen.getByRole('button', { name: /use this video/i }));

  await screen.findByTestId('tag-picker');
  return user;
}

it('all five tags rendered in tag picker', async () => {
  await reachTaggingPhase();

  const picker = screen.getByTestId('tag-picker');
  const radios = picker.querySelectorAll('input[type="radio"]');
  expect(radios).toHaveLength(5);

  for (const { label } of USAGE_TAGS) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});

it('no default tag is selected', async () => {
  await reachTaggingPhase();

  const radios = screen.getByTestId('tag-picker').querySelectorAll('input[type="radio"]');
  for (const radio of radios) {
    expect(radio).not.toBeChecked();
  }
});

it('upload button is disabled without a tag selected', async () => {
  await reachTaggingPhase();

  const uploadBtn = screen.getByTestId('upload-btn');
  expect(uploadBtn).toBeDisabled();
});

it('onCapture called with video blob and tag after submit', async () => {
  const onCapture = jest.fn();
  const user = await reachTaggingPhase(onCapture);

  // Select a tag
  await user.click(screen.getByText('Brand asset'));

  const uploadBtn = screen.getByTestId('upload-btn');
  expect(uploadBtn).not.toBeDisabled();

  await user.click(uploadBtn);

  expect(onCapture).toHaveBeenCalledTimes(1);
  expect(onCapture).toHaveBeenCalledWith(
    expect.any(Blob),
    'brand_asset',
  );

  // Should return to idle
  expect(screen.queryByTestId('snippet-overlay')).not.toBeInTheDocument();
});
