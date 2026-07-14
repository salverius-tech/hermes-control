export type NavigationItem = {
  href: '/' | '/attention' | '/new-task' | '/projects';
  label: string;
  iconName: 'home' | 'list' | 'bell' | 'plus-circle' | 'folder';
  replace?: boolean;
};

export const navigationItems: NavigationItem[] = [
  { href: '/', label: 'Home', iconName: 'home', replace: true },
  { href: '/attention', label: 'Attention', iconName: 'bell', replace: true },
  { href: '/new-task', label: 'New', iconName: 'plus-circle', replace: true },
  { href: '/projects', label: 'Projects', iconName: 'folder', replace: true },
];

export function isActiveRoute(pathname: string, href: NavigationItem['href']): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}
