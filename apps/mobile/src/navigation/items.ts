export type NavigationItem = {
  href: '/' | '/tasks' | '/attention' | '/new-task' | '/projects' | '/more';
  label: string;
  iconName: 'home' | 'list' | 'bell' | 'plus-circle' | 'folder';
  badge?: 'attention';
  replace?: boolean;
};

export const navigationItems: NavigationItem[] = [
  { href: '/', label: 'Inbox', iconName: 'home', badge: 'attention', replace: true },
  { href: '/projects', label: 'Projects', iconName: 'folder', replace: true },
  { href: '/new-task', label: 'New', iconName: 'plus-circle', replace: true },
  { href: '/tasks', label: 'Activity', iconName: 'list', replace: true },
  { href: '/more', label: 'More', iconName: 'bell', replace: true },
];

export function isActiveRoute(pathname: string, href: NavigationItem['href']): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}
