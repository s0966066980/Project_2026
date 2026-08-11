import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

const frontendRoot = resolve(import.meta.dirname, '../..');
const productRoots = {
  admin: resolve(frontendRoot, 'admin'),
  kiosk: resolve(frontendRoot, 'kiosk'),
};
const sharedRoot = resolve(frontendRoot, 'shared');
const importPattern = /\b(?:from\s+|import\s*\()\s*['"]([^'"]+)['"]/g;

function sourceFiles(root: string): string[] {
  return readdirSync(root).flatMap((name) => {
    const path = resolve(root, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(?:js|ts)$/.test(name) ? [path] : [];
  });
}

function importedPaths(path: string): string[] {
  const source = readFileSync(path, 'utf8');
  return Array.from(source.matchAll(importPattern), (match) => match[1])
    .filter((specifier): specifier is string => typeof specifier === 'string')
    .filter((specifier) => specifier.startsWith('.'))
    .map((specifier) => resolve(dirname(path), specifier));
}

function isWithin(path: string, root: string): boolean {
  const pathFromRoot = relative(root, path);
  return pathFromRoot === '' || (!pathFromRoot.startsWith(`..${sep}`) && pathFromRoot !== '..');
}

describe('independent product frontend boundaries', () => {
  it.each([
    ['admin', 'kiosk'],
    ['kiosk', 'admin'],
  ] as const)('%s does not import the %s product', (sourceProduct, targetProduct) => {
    const violations = sourceFiles(productRoots[sourceProduct]).flatMap((path) =>
      importedPaths(path)
        .filter((imported) => isWithin(imported, productRoots[targetProduct]))
        .map((imported) => `${relative(frontendRoot, path)} -> ${relative(frontendRoot, imported)}`),
    );
    expect(violations).toEqual([]);
  });

  it('shared foundation does not import either product', () => {
    const violations = sourceFiles(sharedRoot).flatMap((path) =>
      importedPaths(path)
        .filter((imported) => Object.values(productRoots).some((root) => isWithin(imported, root)))
        .map((imported) => `${relative(frontendRoot, path)} -> ${relative(frontendRoot, imported)}`),
    );
    expect(violations).toEqual([]);
  });
});

/**
 * Admin used to run inside the kiosk bundle behind `isAdminMode()`. Admin is
 * its own application (ADR-0024), so those branches were unreachable code that
 * still had to be read and maintained by anyone touching the kiosk.
 */
describe('the kiosk bundle carries no Admin runtime mode', () => {
  const kioskSources = () => sourceFiles(productRoots.kiosk);

  it('no kiosk source decides behaviour by admin mode', () => {
    const offenders = kioskSources().filter((path) => /\bisAdminMode\b/.test(readFileSync(path, 'utf8')));
    expect(offenders.map((path) => relative(frontendRoot, path))).toEqual([]);
  });

  it('the shared surface holds no admin view for the kiosk to switch into', () => {
    const shared = sourceFiles(sharedRoot)
      .filter((path) => /\badminView\b|\badminNotificationBox\b|loadAdminData/.test(readFileSync(path, 'utf8')));
    expect(shared.map((path) => relative(frontendRoot, path))).toEqual([]);
  });
});

/**
 * Gate 7: Admin and Kiosk reach the catalog through the generated contract.
 * A raw call to the legacy route would keep working, which is exactly why it
 * has to fail here instead.
 */
describe('catalog callers use the generated contract', () => {
  const LEGACY_CATALOG_ROUTES = /['"`][^'"`]*\/api\/(menu|availability)\b/;

  it('no product calls the legacy catalog routes directly', () => {
    const offenders = [...sourceFiles(productRoots.admin), ...sourceFiles(productRoots.kiosk), ...sourceFiles(sharedRoot)]
      .filter((path) => LEGACY_CATALOG_ROUTES.test(readFileSync(path, 'utf8')))
      .map((path) => relative(frontendRoot, path));
    expect(offenders).toEqual([]);
  });

  it('the catalog client is the only place that spells the v1 catalog path', () => {
    const spellers = [...sourceFiles(productRoots.admin), ...sourceFiles(productRoots.kiosk), ...sourceFiles(sharedRoot)]
      .filter((path) => /\/api\/v1\/catalog/.test(readFileSync(path, 'utf8')))
      .map((path) => relative(frontendRoot, path));
    expect(spellers).toEqual(['shared/api/catalogClient.js']);
  });
});
