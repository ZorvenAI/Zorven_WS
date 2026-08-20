/**
 * H-01 · useCaptureQueue — offline-aware upload queue.
 */

import { act, renderHook, waitFor } from '@testing-library/react';

import { useCaptureQueue } from '@/hooks/useCaptureQueue';
import * as sessions from '@/lib/onboarding-sessions';

jest.mock('@/lib/onboarding-sessions', () => ({
  ...jest.requireActual('@/lib/onboarding-sessions'),
  uploadCapture: jest.fn(),
}));

const mockUpload = sessions.uploadCapture as jest.MockedFunction<
  typeof sessions.uploadCapture
>;

afterEach(() => {
  jest.clearAllMocks();
});

it('enqueue calls uploadCapture', async () => {
  mockUpload.mockResolvedValue({
    id: '42',
    file_name: 'test.jpg',
    usage_tag: 'business_photo',
    file_size: 1024,
    uploaded_at: '2026-08-01T00:00:00Z',
  });

  const { result } = renderHook(() => useCaptureQueue('session-1'));

  act(() => {
    result.current.enqueue(
      new Blob(['img'], { type: 'image/jpeg' }),
      'business_photo',
      'test.jpg',
    );
  });

  await waitFor(() => {
    expect(mockUpload).toHaveBeenCalledTimes(1);
    expect(result.current.captures).toHaveLength(1);
    expect(result.current.captures[0].usage_tag).toBe('business_photo');
  });
});

it('failed upload retries', async () => {
  mockUpload
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({
      id: '43',
      file_name: 'retry.jpg',
      usage_tag: 'other',
      file_size: 512,
      uploaded_at: '2026-08-01T00:00:00Z',
    });

  jest.useFakeTimers();

  const { result } = renderHook(() => useCaptureQueue('session-1'));

  act(() => {
    result.current.enqueue(
      new Blob(['img'], { type: 'image/jpeg' }),
      'other',
      'retry.jpg',
    );
  });

  // First attempt fails, triggers retry with backoff
  await waitFor(() => {
    expect(mockUpload).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe('error');
  });

  // Advance past backoff timer
  act(() => {
    jest.advanceTimersByTime(5000);
  });

  await waitFor(() => {
    expect(mockUpload).toHaveBeenCalledTimes(2);
    expect(result.current.captures).toHaveLength(1);
  });

  jest.useRealTimers();
});

it('online event triggers drain', async () => {
  mockUpload.mockRejectedValueOnce(new Error('offline'));

  jest.useFakeTimers();

  const { result } = renderHook(() => useCaptureQueue('session-1'));

  act(() => {
    result.current.enqueue(
      new Blob(['img'], { type: 'image/jpeg' }),
      'brand_asset',
      'online.jpg',
    );
  });

  await waitFor(() => {
    expect(result.current.status).toBe('error');
  });

  // Simulate coming back online
  mockUpload.mockResolvedValueOnce({
    id: '44',
    file_name: 'online.jpg',
    usage_tag: 'brand_asset',
    file_size: 256,
    uploaded_at: '2026-08-01T00:00:00Z',
  });

  act(() => {
    window.dispatchEvent(new Event('online'));
  });

  await waitFor(() => {
    expect(result.current.captures).toHaveLength(1);
  });

  jest.useRealTimers();
});

it('tag is preserved through retry', async () => {
  mockUpload
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({
      id: '45',
      file_name: 'tagged.jpg',
      usage_tag: 'identity_document',
      file_size: 4096,
      uploaded_at: '2026-08-01T00:00:00Z',
    });

  jest.useFakeTimers();

  const { result } = renderHook(() => useCaptureQueue('session-1'));

  act(() => {
    result.current.enqueue(
      new Blob(['img'], { type: 'image/jpeg' }),
      'identity_document',
      'tagged.jpg',
    );
  });

  await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(1));

  act(() => {
    jest.advanceTimersByTime(5000);
  });

  await waitFor(() => {
    expect(mockUpload).toHaveBeenCalledTimes(2);
    expect(result.current.captures[0].usage_tag).toBe('identity_document');
  });

  jest.useRealTimers();
});
