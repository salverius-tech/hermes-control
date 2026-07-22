import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('offline queue Maestro selectors', () => {
  it('assigns deterministic selectors to queued submission controls', () => {
    const source = readFileSync(join(process.cwd(), 'app', 'tasks', 'index.tsx'), 'utf8');

    expect(source).toContain('testID={`queued-task-${item.local_id}`}');
    expect(source).toContain('testID={`queued-task-retry-${item.local_id}`}');
    expect(source).toContain('testID={`queued-task-discard-${item.local_id}`}');
  });
});
