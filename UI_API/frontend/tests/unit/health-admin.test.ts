import { describe, expect, it, vi } from 'vitest';

import {
  createHealthAdmin,
  healthLabel,
  serviceHealthSummary,
  serviceHealthView,
} from '../../admin/modules/healthAdmin.js';

/** Drives the panel's own clock so a bounded wait can be observed without spending it. */
function createTestTimers() {
  let sequence = 0;
  const pending = new Map<number, { at: number; run: () => void }>();
  let now = 0;
  return {
    timers: {
      setTimeout: ((run: () => void, delay = 0) => {
        const handle = ++sequence;
        pending.set(handle, { at: now + delay, run });
        return handle as unknown as ReturnType<typeof setTimeout>;
      }) as unknown as typeof setTimeout,
      clearTimeout: ((handle: unknown) => {
        pending.delete(handle as number);
      }) as unknown as typeof clearTimeout,
    },
    async advance(ms: number) {
      now += ms;
      for (const [handle, entry] of [...pending.entries()]) {
        if (entry.at > now) continue;
        pending.delete(handle);
        entry.run();
      }
      for (let tick = 0; tick < 8; tick += 1) await Promise.resolve();
    },
  };
}

const service = (overrides = {}) => ({
  key: 'ollama',
  label: 'Ollama 文字模型',
  status: 'ok',
  latency_ms: 42,
  observed_at: '2026-08-07T02:30:00+00:00',
  safe_error: '',
  ...overrides,
});

describe('service health rows', () => {
  it('shows latency, observation time and status for each service', () => {
    const [row] = serviceHealthView([service()]);

    expect(row?.label).toBe('Ollama 文字模型');
    expect(row?.statusLabel).toBe('正常');
    expect(row?.latency).toBe('42 ms');
    expect(row?.observedAt).not.toBe('尚未觀測');
  });

  // A service with no measurement must not render as instant.
  it('shows a dash rather than zero when latency was not measured', () => {
    const [row] = serviceHealthView([service({ latency_ms: null })]);

    expect(row?.latency).toBe('—');
  });

  it('says so plainly when nothing has been observed yet', () => {
    const [row] = serviceHealthView([service({ observed_at: '' })]);

    expect(row?.observedAt).toBe('尚未觀測');
  });

  it('carries the safe error through untouched', () => {
    const [row] = serviceHealthView([service({ status: 'down', safe_error: 'URLError' })]);

    expect(row?.safeError).toBe('URLError');
  });

  it('names every status the backend can send', () => {
    expect(healthLabel('ok')).toBe('正常');
    expect(healthLabel('degraded')).toBe('降級');
    expect(healthLabel('down')).toBe('無回應');
    expect(healthLabel('unknown')).toBe('未觀測');
    expect(healthLabel('not_configured')).toBe('未設定');
    expect(healthLabel('something-else')).toBe('未知');
  });
});

describe('service health summary', () => {
  it('names the service that stopped answering', () => {
    const summary = serviceHealthSummary([
      service(),
      service({ key: 'r1_omni', label: 'R1-Omni 情緒模型', status: 'down' }),
    ]);

    expect(summary.tone).toBe('not_ready');
    expect(summary.headline).toContain('R1-Omni 情緒模型');
  });

  // An outage outranks a slowdown: the operator should be sent to the harder problem.
  it('reports an outage ahead of a slow service', () => {
    const summary = serviceHealthSummary([
      service({ status: 'degraded' }),
      service({ key: 'r1_omni', label: 'R1-Omni 情緒模型', status: 'down' }),
    ]);

    expect(summary.tone).toBe('not_ready');
    expect(summary.headline).not.toContain('Ollama');
  });

  // A deployment that simply does not run a service is not a fault, and reporting it
  // as one sends someone to fix nothing.
  it('does not treat an unconfigured service as a problem', () => {
    const summary = serviceHealthSummary([
      service(),
      service({ key: 'r1_omni', label: 'R1-Omni 情緒模型', status: 'not_configured' }),
    ]);

    expect(summary.tone).toBe('ok');
  });

  it('flags an unobserved service without calling it broken', () => {
    const summary = serviceHealthSummary([service(), service({ key: 'r1_omni', status: 'unknown' })]);

    expect(summary.tone).toBe('skipped');
    expect(summary.headline).toContain('尚未觀測');
  });

  it('says nothing conclusive before any service has been read', () => {
    expect(serviceHealthSummary([]).tone).toBe('skipped');
  });

  it('confirms health only when every service answers', () => {
    const summary = serviceHealthSummary([service(), service({ key: 'ui_api' })]);

    expect(summary.tone).toBe('ok');
    expect(summary.headline).toContain('都正常');
  });
});

// The panel that tells an operator which dependency stopped answering must not
// itself be able to hang on a service that accepts the connection and goes quiet.
describe('maintenance health read', () => {
  const panelWith = (fetchImpl: unknown, timers: ReturnType<typeof createTestTimers>) => {
    const text = new Map<string, string>();
    const elements = new Map<string, { className: string; textContent: string; innerHTML: string }>();
    const panel = createHealthAdmin({
      apiBaseUrl: 'http://api',
      adminHeaders: () => ({}),
      getElement: ((id: string) => {
        if (!elements.has(id)) elements.set(id, { className: '', textContent: '', innerHTML: '' });
        return elements.get(id) ?? null;
      }) as unknown as (id: string) => HTMLElement | null,
      setText: (id: string, value: string) => text.set(id, value),
      escapeHtml: (value: string) => String(value),
      hasPermission: () => true,
      fetchImpl: fetchImpl as typeof fetch,
      timers: timers.timers,
    });
    return { panel, text, elements };
  };

  it('reaches a bounded failure when the service-health read never answers', async () => {
    const timers = createTestTimers();
    const { panel, text, elements } = panelWith(() => new Promise<never>(() => {}), timers);

    const settled = panel.loadAdminHealth();
    await timers.advance(5000);
    await settled;

    expect(text.get('healthGeneratedAt')).toBe('本次更新失敗');
    expect(elements.get('healthOverallStatus')?.className).toContain('not_ready');
  });

  it('recovers when an operator retries after a timed-out read', async () => {
    const timers = createTestTimers();
    const fetchImpl = vi.fn()
      .mockImplementationOnce(() => new Promise<never>(() => {}))
      .mockImplementationOnce(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ data: { services: [service()] } }),
      }));
    const { panel, text, elements } = panelWith(fetchImpl, timers);

    const firstRead = panel.loadAdminHealth();
    await timers.advance(5000);
    await firstRead;
    expect(text.get('healthGeneratedAt')).toBe('本次更新失敗');

    await panel.loadAdminHealth();

    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(text.get('healthGeneratedAt')).toContain('更新於');
    expect(elements.get('healthOverallStatus')?.className).toContain('ok');
  });

  it('renders the services when the read answers', async () => {
    const timers = createTestTimers();
    const { panel, text } = panelWith(
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ data: { services: [service()] } }),
      })),
      timers,
    );

    await panel.loadAdminHealth();

    expect(text.get('healthGeneratedAt')).toContain('更新於');
  });
});
