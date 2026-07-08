import { describe, expect, it } from 'vitest';

import { isActiveRoute, navigationItems } from './items';

describe('navigationItems', () => {
  it('keeps primary screens reachable from the bottom bar', () => {
    expect(navigationItems.map((item) => item.href)).toEqual(['/', '/tasks', '/new-task', '/projects', '/settings']);
  });
});

describe('isActiveRoute', () => {
  it('marks the dashboard active only at the root route', () => {
    expect(isActiveRoute('/', '/')).toBe(true);
    expect(isActiveRoute('/tasks', '/')).toBe(false);
  });

  it('marks nested screens active under their parent route', () => {
    expect(isActiveRoute('/tasks/task-123', '/tasks')).toBe(true);
  });

  it('does not mark sibling routes as active', () => {
    expect(isActiveRoute('/projects', '/tasks')).toBe(false);
  });
});
