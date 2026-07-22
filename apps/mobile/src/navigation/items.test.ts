import { describe, expect, it } from 'vitest';

import { isActiveRoute, navigationItems } from './items';

describe('navigationItems', () => {
  it('keeps primary screens reachable from the bottom bar', () => {
    expect(navigationItems.map((item) => item.href)).toEqual(['/', '/projects', '/new-task', '/tasks', '/more']);
  });

  it('replaces navigation history when returning home from the bottom bar', () => {
    expect(navigationItems.find((item) => item.href === '/')?.replace).toBe(true);
  });

  it('uses replace navigation for each primary bottom bar destination', () => {
    expect(navigationItems.every((item) => item.replace)).toBe(true);
  });

  it('uses named vector icons instead of font glyphs', () => {
    expect(navigationItems.map((item) => item.iconName)).toEqual(['home', 'folder', 'plus-circle', 'list', 'bell']);
  });
});

describe('isActiveRoute', () => {
  it('marks the dashboard active only at the root route', () => {
    expect(isActiveRoute('/', '/')).toBe(true);
    expect(isActiveRoute('/attention', '/')).toBe(false);
  });

  it('marks nested screens active under their parent route', () => {
    expect(isActiveRoute('/attention/task-123', '/attention')).toBe(true);
  });

  it('does not mark sibling routes as active', () => {
    expect(isActiveRoute('/projects', '/attention')).toBe(false);
  });
});
