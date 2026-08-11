import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * A refused Voice Turn must reach the kiosk with the reason the service gave.
 * Collapsing every refusal into `HTTP 503` leaves the kiosk unable to tell a
 * capability that is still starting from one that failed — and those call for
 * different things from the customer standing at the machine.
 */

const emptyStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

Object.assign(globalThis, {
  window: {
    location: { protocol: 'http:', pathname: '/kiosk', hash: '', origin: 'http://api' },
  },
  history: { replaceState: () => {} },
  sessionStorage: emptyStorage,
  localStorage: emptyStorage,
});

const { streamVoiceAssistantResponse } = await import('../../shared/apiClient.js');

function refusalResponse(status: number, body: unknown) {
  return {
    ok: false,
    status,
    body: null,
    json: async () => body,
  };
}

const handlers = () => ({
  onEvent: vi.fn(),
  onAudio: vi.fn(),
  onTranscript: vi.fn(),
  onAssistantText: vi.fn(),
  onDone: vi.fn(),
  onError: vi.fn(),
});

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('voice turn refusal', () => {
  it('carries a warming capability through as its own reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => refusalResponse(503, {
      detail: { code: 'voice_capability_warming' },
    })));
    const callbacks = handlers();
    const formData = new FormData();
    formData.append('voice_turn_id', '');

    await expect(streamVoiceAssistantResponse(formData, callbacks)).rejects.toThrow();

    expect(callbacks.onError).toHaveBeenCalledWith(
      expect.stringContaining('voice_capability_warming'),
      { status: 503, code: 'voice_capability_warming' },
    );
  });

  it('still reports a refusal that carries no reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => refusalResponse(500, 'not json at all')));
    const callbacks = handlers();
    const formData = new FormData();
    formData.append('voice_turn_id', '');

    await expect(streamVoiceAssistantResponse(formData, callbacks)).rejects.toThrow();

    expect(callbacks.onError).toHaveBeenCalledWith(
      expect.stringContaining('500'),
      { status: 500, code: '' },
    );
  });
});
