import { Feather } from '@expo/vector-icons';
import { Link, type Href, usePathname } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing } from '@/theme/tokens';
import { useDataStore } from '@/state/data-store';

import { bottomNavigationHeight } from './constants';
import { isActiveRoute, navigationItems } from './items';

export function BottomNavigation() {
  const pathname = usePathname();
  const insets = useSafeAreaInsets();
  const unreadAttention = useDataStore((state) => state.unreadAttention);
  const showNavigation = pathname === '/' || pathname === '/tasks' || pathname === '/attention' || pathname === '/new-task' || pathname === '/projects' || pathname === '/more';

  if (!showNavigation) return null;

  return (
    <View style={[styles.shell, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}> 
      <View style={styles.bar}>
        {navigationItems.map((item) => {
          const active = isActiveRoute(pathname, item.href);
          return (
            <View key={item.label} style={styles.slot}>
              <Link href={item.href as Href} replace={item.replace} asChild>
                <Pressable
                  accessibilityLabel={item.badge === 'attention' && unreadAttention > 0 ? `${item.label}, ${unreadAttention} unread attention items` : item.label}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  testID={`nav-${item.label.toLowerCase()}`}
                  style={({ pressed }) => [styles.item, active && styles.activeItem, pressed && styles.pressed]}
                >
                  <View style={styles.stack}>
                    <Feather color={active ? colors.text : colors.muted} name={item.iconName} size={28} style={styles.icon} />
                    <Text style={[styles.label, active && styles.activeText]}>{item.label}</Text>
                    {item.badge === 'attention' && unreadAttention > 0 ? <View accessibilityLabel={`${unreadAttention} unread attention items`} style={styles.badge}><Text style={styles.badgeText}>{unreadAttention > 9 ? '9+' : unreadAttention}</Text></View> : null}
                  </View>
                </Pressable>
              </Link>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { alignItems: 'center', backgroundColor: colors.danger, borderRadius: 999, minWidth: 18, paddingHorizontal: 4, position: 'absolute', right: 4, top: 0 },
  badgeText: { color: colors.text, fontSize: 10, fontWeight: '900' },
  activeItem: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  activeText: {
    color: colors.text,
  },
  bar: {
    alignItems: 'center',
    backgroundColor: colors.elevated,
    borderColor: colors.border,
    borderRadius: 28,
    borderWidth: 1,
    flexDirection: 'row',
    height: bottomNavigationHeight,
    padding: spacing.sm,
    shadowColor: '#000',
    shadowOffset: { height: 8, width: 0 },
    shadowOpacity: 0.28,
    shadowRadius: 16,
  },
  icon: {
    textAlign: 'center',
    width: '100%',
  },
  item: {
    alignItems: 'stretch',
    borderColor: 'transparent',
    borderRadius: 18,
    borderWidth: 1,
    height: '100%',
    justifyContent: 'center',
    width: '100%',
  },
  label: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '800',
    textAlign: 'center',
    width: '100%',
  },
  pressed: {
    opacity: 0.78,
  },
  shell: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  slot: {
    flex: 1,
    height: '100%',
    paddingHorizontal: spacing.xs,
  },
  stack: {
    alignItems: 'stretch',
    gap: 2,
    justifyContent: 'center',
    width: '100%',
  },
});
