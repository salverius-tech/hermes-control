import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('new-task Maestro project selector', () => {
  it('assigns a deterministic selector to each native project choice', () => {
    const source = readFileSync(join(process.cwd(), 'app', 'new-task.tsx'), 'utf8');

    expect(source).toContain('testID={`new-task-project-${project.project_id}`}');
  });

  it('synchronizes the displayed queue after persisting an unavailable submission', () => {
    const source = readFileSync(join(process.cwd(), 'app', 'new-task.tsx'), 'utf8');

    expect(source).toContain('const syncQueuedTasks = useDataStore((state) => state.syncQueuedTasks);');
    expect(source).toContain('await enqueueTask(AsyncStorage, request, new Date(), idempotencyKey);\n          await syncQueuedTasks();');
  });
});
