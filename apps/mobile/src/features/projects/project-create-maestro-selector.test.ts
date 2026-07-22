import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(__dirname, '../../../app/projects/manage.tsx'), 'utf8');
const listSource = readFileSync(resolve(__dirname, '../../../app/projects/index.tsx'), 'utf8');

describe('project creation Maestro selectors', () => {
  it('keeps stable selectors for workspace and clone creation inputs and actions', () => {
    expect(source).toContain('testID="project-create-name"');
    expect(source).toContain('testID={`project-origin-${item}`}');
    expect(source).toContain('testID="project-create-repository-url"');
    expect(source).toContain('testID="project-create-submit"');
    expect(listSource).toContain('testID="project-create-new"');
  });
});
