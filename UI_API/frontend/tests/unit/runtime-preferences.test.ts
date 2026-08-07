import { beforeEach, describe, expect, it } from 'vitest';

import {
  buildKioskSessionId,
  loadKioskFeatures,
  resolveKioskAppMode,
  saveKioskFeatures,
} from '../../kiosk/features/bootstrap/runtimePreferences.js';

class MemoryStorage {
  private readonly entries = new Map<string, string>();

  getItem(key: string): string | null {
    return this.entries.has(key) ? String(this.entries.get(key)) : null;
  }

  setItem(key: string, value: string): void {
    this.entries.set(key, String(value));
  }

  removeItem(key: string): void {
    this.entries.delete(key);
  }

  clear(): void {
    this.entries.clear();
  }

  get length(): number {
    return this.entries.size;
  }

  key(index: number): string | null {
    return Array.from(this.entries.keys())[index] ?? null;
  }
}

let storage: MemoryStorage;

function asStorage(instance: MemoryStorage): Storage {
  return instance as unknown as Storage;
}

function asLocation(values: { port?: string; pathname?: string; search?: string }): Location {
  return { port: '', pathname: '/', search: '', ...values } as Location;
}

beforeEach(() => {
  storage = new MemoryStorage();
});

describe('kiosk app mode', () => {
  it('serves admin on its own port and path', () => {
    expect(resolveKioskAppMode(asLocation({ port: '9001' }))).toBe('admin');
    expect(resolveKioskAppMode(asLocation({ pathname: '/admin/settings' }))).toBe('admin');
  });

  it('serves kiosk everywhere else', () => {
    expect(resolveKioskAppMode(asLocation({ pathname: '/kiosk' }))).toBe('kiosk');
    expect(resolveKioskAppMode(asLocation({ port: '9080', pathname: '/' }))).toBe('kiosk');
  });
});

describe('kiosk session id', () => {
  it('keeps a requested id that is already safe', () => {
    expect(buildKioskSessionId(asLocation({ search: '?session_id=kiosk_abc-123' }))).toBe('kiosk_abc-123');
  });

  // The id reaches the server and lands in logs, so anything a URL can carry is stripped.
  it('strips unsafe characters rather than rejecting the request', () => {
    expect(buildKioskSessionId(asLocation({ search: '?session_id=drop/../table;--' }))).toBe('droptable--');
  });

  it('caps the length at 80 characters', () => {
    const long = 'a'.repeat(200);
    expect(buildKioskSessionId(asLocation({ search: `?session_id=${long}` }))).toHaveLength(80);
  });

  it('generates an id when none is requested or nothing survives sanitising', () => {
    expect(buildKioskSessionId(asLocation({}))).toMatch(/^kiosk_[a-z0-9]+$/);
    expect(buildKioskSessionId(asLocation({ search: '?session_id=///' }))).toMatch(/^kiosk_[a-z0-9]+$/);
  });
});

describe('kiosk feature preferences', () => {
  it('starts from defaults and persists them with the schema version', () => {
    expect(loadKioskFeatures(asStorage(storage), false)).toEqual({ voiceAssist: true, recommend: true });
    expect(storage.getItem('kiosk_feat_version')).toBe('voice-emotion-20260721');
  });

  it('restores saved choices', () => {
    saveKioskFeatures(asStorage(storage), { voiceAssist: false, recommend: true });

    expect(loadKioskFeatures(asStorage(storage), false)).toEqual({ voiceAssist: false, recommend: true });
  });

  it('ignores stored values that are not booleans', () => {
    storage.setItem('kiosk_feat', JSON.stringify({ voiceAssist: 'yes', recommend: false }));
    storage.setItem('kiosk_feat_version', 'voice-emotion-20260721');

    expect(loadKioskFeatures(asStorage(storage), false)).toEqual({ voiceAssist: true, recommend: false });
  });

  it('ignores keys the schema does not define', () => {
    storage.setItem('kiosk_feat', JSON.stringify({ voiceAssist: false, emotion: true }));
    storage.setItem('kiosk_feat_version', 'voice-emotion-20260721');

    expect(loadKioskFeatures(asStorage(storage), false)).toEqual({ voiceAssist: false, recommend: true });
  });

  // A stale schema means the saved shape predates the current feature set.
  it('rewrites storage when the saved schema version is stale', () => {
    storage.setItem('kiosk_feat', JSON.stringify({ voiceAssist: false, recommend: false }));
    storage.setItem('kiosk_feat_version', 'older-version');

    expect(loadKioskFeatures(asStorage(storage), false)).toEqual({ voiceAssist: false, recommend: false });
    expect(storage.getItem('kiosk_feat_version')).toBe('voice-emotion-20260721');
  });

  it('turns both features on for a fresh public demo', () => {
    expect(loadKioskFeatures(asStorage(storage), true)).toEqual({ voiceAssist: true, recommend: true });
  });

  it('does not override a demo visitor who already made a choice', () => {
    saveKioskFeatures(asStorage(storage), { voiceAssist: false, recommend: false });

    expect(loadKioskFeatures(asStorage(storage), true)).toEqual({ voiceAssist: false, recommend: false });
  });

  it('falls back to defaults when storage is unusable', () => {
    const brokenStorage = {
      getItem() { throw new Error('storage_disabled'); },
      setItem() { throw new Error('storage_disabled'); },
    } as unknown as Storage;

    expect(loadKioskFeatures(brokenStorage, false)).toEqual({ voiceAssist: true, recommend: true });
  });

  it('falls back to defaults when the stored value is not JSON', () => {
    storage.setItem('kiosk_feat', 'not json');

    expect(loadKioskFeatures(asStorage(storage), false)).toEqual({ voiceAssist: true, recommend: true });
  });
});
