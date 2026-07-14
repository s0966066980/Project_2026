import { afterEach, describe, expect, it, vi } from 'vitest';

import { observeVisibleImpression } from '../../shared/touchEventClient.js';

describe('visible impression threshold', () => {
  afterEach(() => vi.useRealTimers());

  it('requires 50 percent visibility for one second and sends once', () => {
    vi.useFakeTimers();
    const element = {} as Element;
    const onVisible = vi.fn();
    let callback: IntersectionObserverCallback = () => {};
    const disconnect = vi.fn();
    observeVisibleImpression(element, {
      onVisible,
      observerFactory(nextCallback) {
        callback = nextCallback;
        return { observe: vi.fn(), disconnect };
      },
    });

    callback([{ target: element, isIntersecting: true, intersectionRatio: 0.49 } as IntersectionObserverEntry], {} as IntersectionObserver);
    vi.advanceTimersByTime(1200);
    expect(onVisible).not.toHaveBeenCalled();

    callback([{ target: element, isIntersecting: true, intersectionRatio: 0.5 } as IntersectionObserverEntry], {} as IntersectionObserver);
    vi.advanceTimersByTime(999);
    expect(onVisible).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onVisible).toHaveBeenCalledTimes(1);
    expect(disconnect).toHaveBeenCalled();
  });
});
