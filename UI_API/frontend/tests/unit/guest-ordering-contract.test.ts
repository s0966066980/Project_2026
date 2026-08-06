import { describe, expect, it, vi } from 'vitest';

import { completeGuestOrderingChoice } from '../../kiosk/guestOrdering.js';

describe('guest ordering choice', () => {
  it('starts ordering only after the server accepts the shared guest command', async () => {
    const onAccepted = vi.fn();
    const chooseGuest = vi.fn(async () => ({ state: 'initializing_menu' }));

    await expect(completeGuestOrderingChoice({ chooseGuest, onAccepted })).resolves.toBe(true);
    expect(chooseGuest).toHaveBeenCalledOnce();
    expect(onAccepted).toHaveBeenCalledOnce();
  });

  it('keeps the choice recoverable when the command fails', async () => {
    const onAccepted = vi.fn();
    const onRejected = vi.fn();

    await expect(completeGuestOrderingChoice({
      chooseGuest: async () => { throw new Error('offline'); },
      onAccepted,
      onRejected,
    })).resolves.toBe(false);
    expect(onAccepted).not.toHaveBeenCalled();
    expect(onRejected).toHaveBeenCalledOnce();
  });
});
