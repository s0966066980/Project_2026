import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const root = resolve(import.meta.dirname, '../..');

function javascriptSources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) return javascriptSources(path);
    return entry.name.endsWith('.js') ? [readFileSync(path, 'utf8')] : [];
  });
}

describe('frontend feature boundaries', () => {
  it('extracts Kiosk bootstrap preferences and Admin auth from coordinators', () => {
    expect(existsSync(resolve(root, 'kiosk/features/bootstrap/runtimePreferences.js'))).toBe(true);
    expect(existsSync(resolve(root, 'admin/features/auth/adminAuth.js'))).toBe(true);
    expect(readFileSync(resolve(root, 'kiosk/app.js'), 'utf8')).not.toContain('const FEAT_DEFAULTS =');
    expect(readFileSync(resolve(root, 'admin/admin.js'), 'utf8')).not.toContain('async function bootstrapAdminSession');
  });

  it('does not allow Kiosk and Admin feature imports to cross application boundaries', () => {
    for (const kiosk of javascriptSources(resolve(root, 'kiosk'))) {
      expect(kiosk).not.toMatch(/from ['"].*admin\//);
    }
    for (const admin of javascriptSources(resolve(root, 'admin'))) {
      expect(admin).not.toMatch(/from ['"].*kiosk\//);
    }
  });
});
