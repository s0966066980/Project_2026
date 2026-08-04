import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Admin scripts reach for elements by id. When a panel is moved or renamed, an id lookup that
 * no longer resolves fails silently — `getElement(id)?.…` short-circuits and any `|| default`
 * downstream quietly takes over. That is how the model-diagnostic provider selector kept
 * reporting `ollama` after its container was removed: every NVIDIA NIM prompt ran locally, and
 * no test noticed because the assertions only compared source text.
 *
 * This guard checks every id an Admin script looks up against the ids that actually exist —
 * either authored in admin.html or emitted by a script's own template, which covers nodes
 * built at runtime without a hand-maintained allowlist going stale.
 */
const frontendRoot = resolve(__dirname, '../..');

const SCRIPT_PATHS = [
  'admin/admin.js',
  ...readdirSync(resolve(frontendRoot, 'admin/modules'))
    .filter(name => name.endsWith('.js'))
    .map(name => `admin/modules/${name}`),
];

const adminHtml = readFileSync(resolve(frontendRoot, 'admin/admin.html'), 'utf8');
const scripts = SCRIPT_PATHS.map(path => ({
  path,
  source: readFileSync(resolve(frontendRoot, path), 'utf8'),
}));

/** `g('x')`, `setText('x', …)`, `getElement('x')`, `document.getElementById('x')`. */
const LOOKUP_PATTERN = /(?:\bg|\bsetText|\bgetElement|\bdocument\.getElementById)\(\s*'([\w-]+)'/g;
const DEFINITION_PATTERN = /id=["']([\w-]+)["']/g;

function idsMatching(pattern: RegExp, source: string): string[] {
  return [...source.matchAll(pattern)].flatMap(match => (match[1] ? [match[1]] : []));
}

describe('Admin 元素 id 參照', () => {
  const definedIds = new Set([
    ...idsMatching(DEFINITION_PATTERN, adminHtml),
    ...scripts.flatMap(({ source }) => idsMatching(DEFINITION_PATTERN, source)),
  ]);

  it.each(scripts)('$path 查詢的每個 id 都真的存在', ({ path, source }) => {
    const dangling = [...new Set(idsMatching(LOOKUP_PATTERN, source))]
      .filter(id => !definedIds.has(id));
    expect(dangling, `${path} 參照了 admin.html 與腳本模板都沒有的 id`).toEqual([]);
  });

  it('模型診斷的提供者選擇不再依賴 DOM 容器位置', () => {
    const adminJs = scripts.find(({ path }) => path === 'admin/admin.js')!.source;
    // The panel now lives under the settings page; reading the active tab back out of a named
    // container is exactly what broke, so the override is held in module state instead.
    expect(adminJs).not.toContain('page-test');
    expect(adminJs).toMatch(/function getTestProvider\(\)\s*\{\s*return _testProvider;/);
    expect(adminJs).toMatch(/_testProvider = btn\.dataset\.provider/);
  });

  it('診斷的 NIM 模型沿用 NIM 模型目錄', () => {
    expect(adminHtml).toContain('<select id="test-inp-nim-model"');
    const settingsModule = scripts.find(({ path }) => path.endsWith('settingsAdmin.js'))!.source;
    expect(settingsModule).toContain("populateNimSelect('test-inp-nim-model'");
    // A model added to the voice catalog must reach the diagnostic dropdown without a reload.
    expect(settingsModule).toMatch(/if \(isVoice\) populateDiagnosticNimSelect\(/);
  });

  it('目錄外的型號可以只測一次，不寫入設定', () => {
    const adminJs = scripts.find(({ path }) => path === 'admin/admin.js')!.source;
    const settingsModule = scripts.find(({ path }) => path.endsWith('settingsAdmin.js'))!.source;

    expect(adminHtml).toContain('id="test-inp-nim-model-custom"');
    expect(adminHtml).toContain('onchange="onTestNimModelChange()"');
    expect(adminJs).toContain("const TEST_NIM_CUSTOM_MODEL = '__custom__'");
    expect(adminJs).toContain('window.onTestNimModelChange = onTestNimModelChange');

    // The typed id is one-shot: it must never join the persisted Custom NIM Model Entry list.
    const diagnosticPopulate = settingsModule.slice(
      settingsModule.indexOf('function populateDiagnosticNimSelect'),
      settingsModule.indexOf('function addCustomNimModel'),
    );
    expect(diagnosticPopulate).toContain("custom.value = '__custom__'");
    expect(diagnosticPopulate).not.toContain('customVoiceModels.push');
    expect(diagnosticPopulate).not.toContain('markDirty');
  });
});
