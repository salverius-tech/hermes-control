import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const sourceRoot = join(process.cwd(), 'src');
const appRoot = join(process.cwd(), 'app');

function walk(dir: string): string[] {
  return readdirSync(dir)
    .flatMap((entry) => {
      const path = join(dir, entry);
      if (entry === 'node_modules') {
        return [];
      }
      if (statSync(path).isDirectory()) {
        return walk(path);
      }
      return /\.(ts|tsx)$/.test(path) ? [path] : [];
    });
}

function importsFor(path: string): string[] {
  const text = readFileSync(path, 'utf8');
  return [...text.matchAll(/^import\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"];?/gm)].map((match) => match[1]);
}

describe('mobile source layer boundaries', () => {
  it('keeps reusable src modules independent from Expo Router app screens', () => {
    const offenders = walk(sourceRoot).flatMap((path) =>
      importsFor(path)
        .filter((specifier) => specifier.startsWith('../../app') || specifier.startsWith('@/app'))
        .map((specifier) => `${relative(process.cwd(), path)} -> ${specifier}`),
    );

    expect(offenders).toEqual([]);
  });

  it('keeps pure feature and navigation model files free of React Native UI imports', () => {
    const pureFiles = [
      join(sourceRoot, 'features/tasks/prompt.ts'),
      join(sourceRoot, 'navigation/items.ts'),
      join(sourceRoot, 'api/url.ts'),
    ];
    const offenders = pureFiles.flatMap((path) =>
      importsFor(path)
        .filter((specifier) => ['react', 'react-native', 'expo-router'].includes(specifier))
        .map((specifier) => `${relative(process.cwd(), path)} -> ${specifier}`),
    );

    expect(offenders).toEqual([]);
  });

  it('keeps app screens as consumers of src layers rather than importing sibling screen internals', () => {
    const offenders = walk(appRoot).flatMap((path) =>
      importsFor(path)
        .filter((specifier) => specifier.startsWith('../') && !specifier.includes('_layout'))
        .map((specifier) => `${relative(process.cwd(), path)} -> ${specifier}`),
    );

    expect(offenders).toEqual([]);
  });
});
