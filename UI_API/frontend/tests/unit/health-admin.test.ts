import { describe, expect, it } from 'vitest';

import { healthLabel, serviceHealthSummary, serviceHealthView } from '../../admin/modules/healthAdmin.js';

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
