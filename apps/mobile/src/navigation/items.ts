export type NavigationItem = {
  href: '/' | '/tasks' | '/new-task' | '/projects' | '/settings';
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

export function isActiveRoute(pathname: string, href: NavigationItem['href']): boolean {
  const route = href;
  if (route === '/') return pathname === '/';
  return pathname === route || pathname.startsWith(`${route}/`);
}
