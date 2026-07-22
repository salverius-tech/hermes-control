import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('recovery-plan Maestro selectors', () => {
  it('exposes deterministic reviewed-entry and post-confirmation selectors', () => {
    const source = readFileSync(join(process.cwd(), 'app', 'recovery-plan.tsx'), 'utf8');

    expect(source).toContain('testID="recovery-apply-message"');
    expect(source).toContain('testID={`recovery-entry-${entry.slug || entry.status}`}');
  });
});
