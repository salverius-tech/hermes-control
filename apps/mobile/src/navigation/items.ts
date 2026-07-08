import type { Href } from 'expo-router';

export type NavigationItem = {
  href: Href;
  label: string;
  icon: string;
};

export const navigationItems: NavigationItem[] = [
  { href: '/', label: 'Home', icon: '⌂' },
  { href: '/tasks', label: 'Tasks', icon: '▤' },
  { href: '/new-task', label: 'New', icon: '+' },
  { href: '/projects', label: 'Projects', icon: '◇' },
  { href: '/settings', label: 'API', icon: '⚙' },
];

export function isActiveRoute(pathname: string, href: Href): boolean {
  const route = String(href);
  if (route === '/') return pathname === '/';
  return pathname === route || pathname.startsWith(`${route}/`);
}
