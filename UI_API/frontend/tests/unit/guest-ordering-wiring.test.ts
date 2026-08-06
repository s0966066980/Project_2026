import { beforeEach, describe, expect, it, vi } from 'vitest';

// guest-ordering-contract.test.ts covers the helper in isolation. This file covers the
// wiring: it loads the real member.js, clicks the real button ids, and asserts that a
// guest can only reach the menu through a hook the caller actually supplied.

type Listener = () => unknown;

class StubElement {
  disabled = false;
  textContent = '';
  value = '';
  checked = false;
  private readonly attributes = new Map<string, string>();
  private readonly classes = new Set<string>();
  private readonly listeners = new Map<string, Listener[]>();

  readonly classList = {
    add: (...names: string[]) => names.forEach((name) => this.classes.add(name)),
    remove: (...names: string[]) => names.forEach((name) => this.classes.delete(name)),
    contains: (name: string) => this.classes.has(name),
    toggle: (name: string, force?: boolean) => {
      const next = force ?? !this.classes.has(name);
      if (next) this.classes.add(name);
      else this.classes.delete(name);
      return next;
    },
  };

  addEventListener(type: string, listener: Listener) {
    const existing = this.listeners.get(type) ?? [];
    this.listeners.set(type, [...existing, listener]);
  }

  setAttribute(name: string, value: string) { this.attributes.set(name, value); }
  removeAttribute(name: string) { this.attributes.delete(name); }
  getAttribute(name: string) { return this.attributes.get(name) ?? null; }

  async click() {
    for (const listener of this.listeners.get('click') ?? []) await listener();
  }
}

const elements = new Map<string, StubElement>();

function element(id: string): StubElement {
  const existing = elements.get(id);
  if (existing) return existing;
  const created = new StubElement();
  elements.set(id, created);
  return created;
}

const GUEST_BUTTON_IDS = ['memberChoiceGuest', 'memberLoginSkip', 'memberRegisterSkip'] as const;

interface MemberEntryHooks {
  onGuest?: () => Promise<unknown> | unknown;
}

interface MemberModule {
  showMemberChoice: (
    onResolved: (member: unknown) => void,
    options?: { preserveInput?: boolean; hooks?: MemberEntryHooks },
  ) => void;
}

// kiosk/member.js is outside the tsconfig include set. The specifier is kept
// non-literal so loading it here does not pull the whole untyped file into the
// typecheck program; its shape is declared above instead.
const memberModuleSpecifier = ['..', '..', 'kiosk', 'member.js'].join('/');

async function loadMemberModule(): Promise<MemberModule> {
  elements.clear();
  vi.resetModules();
  Object.assign(globalThis, {
    document: { getElementById: (id: string) => element(id) },
    window: { location: { protocol: 'http:', pathname: '/', hash: '', search: '' } },
    history: { replaceState: () => {} },
  });
  return import(memberModuleSpecifier) as Promise<MemberModule>;
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('guest ordering wiring', () => {
  it.each(GUEST_BUTTON_IDS)('%s reaches the menu only after the entry hook accepts', async (buttonId) => {
    const { showMemberChoice } = await loadMemberModule();
    const onGuest = vi.fn(async () => {});
    const resolved = vi.fn();

    showMemberChoice(resolved, { hooks: { onGuest } });
    await element(buttonId).click();

    expect(onGuest).toHaveBeenCalledTimes(1);
    expect(resolved).toHaveBeenCalledWith(null);
  });

  it.each(GUEST_BUTTON_IDS)('%s keeps the customer out of the menu when the server rejects', async (buttonId) => {
    const { showMemberChoice } = await loadMemberModule();
    const onGuest = vi.fn(async () => { throw new Error('entry_flow_unavailable'); });
    const resolved = vi.fn();

    showMemberChoice(resolved, { hooks: { onGuest } });
    await element(buttonId).click();

    expect(onGuest).toHaveBeenCalledTimes(1);
    expect(resolved).not.toHaveBeenCalled();
    expect(element(buttonId).disabled).toBe(false);
  });

  // Regression: showMemberChoice used to default hooks to {}, so a caller that omitted
  // them dropped the customer into the menu without the choice reaching the server.
  it.each(GUEST_BUTTON_IDS)('%s fails visibly when the caller supplied no hooks', async (buttonId) => {
    const { showMemberChoice } = await loadMemberModule();
    const resolved = vi.fn();

    showMemberChoice(resolved);
    await element(buttonId).click();

    expect(resolved).not.toHaveBeenCalled();
    expect(element(buttonId).disabled).toBe(false);
  });

  it('does not discard hooks when a later caller omits them', async () => {
    const { showMemberChoice } = await loadMemberModule();
    const onGuest = vi.fn(async () => {});

    showMemberChoice(vi.fn(), { hooks: { onGuest } });
    const resolved = vi.fn();
    showMemberChoice(resolved);
    await element('memberChoiceGuest').click();

    expect(onGuest).toHaveBeenCalledTimes(1);
    expect(resolved).toHaveBeenCalledWith(null);
  });
});
