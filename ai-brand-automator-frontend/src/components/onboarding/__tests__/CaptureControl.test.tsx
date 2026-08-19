/**
 * H-01 · photo capture with usage tagging.
 *
 * jsdom has no getUserMedia or canvas rendering, so reaching the tagging phase
 * requires mocking the camera stream, canvas getContext, and toBlob. The
 * camera preview and snapshot are faked; the tag picker and submit run real.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import CaptureControl, {
  USAGE_TAGS,
} from '@/components/onboarding/CaptureControl';

const fakeStop = jest.fn();
const fakeStream = { getTracks: () => [{ stop: fakeStop }] };

beforeEach(() => {
  fakeStop.mockClear();
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: jest.fn().mockResolvedValue(fakeStream) },
    writable: true,
    configurable: true,
  });

  // jsdom lacks URL.createObjectURL / revokeObjectURL
  global.URL.createObjectURL = jest.fn(() => 'blob:fake-url');
  global.URL.revokeObjectURL = jest.fn();

  // jsdom has no canvas 2d context — mock createElement to return one
  // that drawImage is callable on and toBlob produces a blob.
  const origCreateElement = document.createElement.bind(document);
  jest.spyOn(document, 'createElement').mockImplementation((tag: string) => {
    const el = origCreateElement(tag);
    if (tag === 'canvas') {
      const fakeCtx = { drawImage: jest.fn() };
      el.getContext = () => fakeCtx;
      el.toBlob = (cb: BlobCallback) => {
        cb(new Blob(['fake-jpeg'], { type: 'image/jpeg' }));
      };
    }
    return el;
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

/**
 * Navigate through camera → take photo → confirm → tagging.
 */
async function reachTaggingPhase(onCapture?: jest.Mock) {
  render(
    <CaptureControl consentGranted={true} onCapture={onCapture} />,
  );

  // Open camera → preview phase
  await userEvent.click(screen.getByRole('button', { name: /capture photo/i }));
  await screen.findByTestId('capture-overlay');

  // Video element needs dimensions for takePhoto
  const video = screen.getByTestId('camera-preview') as HTMLVideoElement;
  Object.defineProperty(video, 'videoWidth', { value: 640 });
  Object.defineProperty(video, 'videoHeight', { value: 480 });

  // Take photo → confirm phase
  await userEvent.click(screen.getByRole('button', { name: /take photo/i }));
  await screen.findByTestId('capture-preview');

  // Confirm → tagging phase
  await userEvent.click(screen.getByRole('button', { name: /use this photo/i }));
  await screen.findByTestId('tag-picker');
}

// ── AC-1 · consent gate ─────────────────────────────────────────────

it('consent gates capture — shows aria-disabled without consent', () => {
  render(<CaptureControl consentGranted={false} />);
  const btn = screen.getByRole('button', { name: /capture photo/i });
  expect(btn).toHaveAttribute('aria-disabled', 'true');
});

it('consent-gated button calls onRecordConsent on click', async () => {
  const onConsent = jest.fn();
  render(
    <CaptureControl consentGranted={false} onRecordConsent={onConsent} />,
  );
  await userEvent.click(screen.getByRole('button', { name: /capture photo/i }));
  expect(onConsent).toHaveBeenCalledTimes(1);
});

it('shows a live capture button when consent is granted', () => {
  render(<CaptureControl consentGranted={true} />);
  const btn = screen.getByRole('button', { name: /capture photo/i });
  expect(btn).not.toHaveAttribute('aria-disabled');
  expect(btn).not.toBeDisabled();
});

// ── AC-1 · overlay opens and dismisses ──────────────────────────────

it('opens camera preview overlay on click', async () => {
  render(<CaptureControl consentGranted={true} />);
  await userEvent.click(screen.getByRole('button', { name: /capture photo/i }));

  expect(await screen.findByTestId('capture-overlay')).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

it('dismiss returns to idle (no overlay)', async () => {
  render(<CaptureControl consentGranted={true} />);
  await userEvent.click(screen.getByRole('button', { name: /capture photo/i }));
  await screen.findByTestId('capture-overlay');
  await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

  expect(screen.queryByTestId('capture-overlay')).not.toBeInTheDocument();
});

// ── AC-2 · tag picker (rendered) ────────────────────────────────────

it('all five tags are rendered in the tag picker', async () => {
  await reachTaggingPhase();

  const picker = screen.getByTestId('tag-picker');
  const radios = picker.querySelectorAll('input[type="radio"]');
  expect(radios).toHaveLength(5);

  for (const { label } of USAGE_TAGS) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});

it('identity_document is not first or last in the rendered tag list', () => {
  const idx = USAGE_TAGS.findIndex((t) => t.value === 'identity_document');
  expect(idx).toBeGreaterThan(0);
  expect(idx).toBeLessThan(USAGE_TAGS.length - 1);
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

// ── AC-3 · onCapture fires through the full rendered flow ───────────

it('onCapture is called with blob and selected tag after submit', async () => {
  const onCapture = jest.fn();
  await reachTaggingPhase(onCapture);

  // Select a tag
  await userEvent.click(screen.getByText('Previous ad'));

  // Upload button should now be enabled
  const uploadBtn = screen.getByTestId('upload-btn');
  expect(uploadBtn).not.toBeDisabled();

  // Submit
  await userEvent.click(uploadBtn);

  expect(onCapture).toHaveBeenCalledTimes(1);
  expect(onCapture).toHaveBeenCalledWith(
    expect.any(Blob),
    'previous_ad',
  );

  // Should return to idle
  expect(screen.queryByTestId('capture-overlay')).not.toBeInTheDocument();
});
