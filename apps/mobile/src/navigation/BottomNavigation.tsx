import { Link, type Href, usePathname } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing } from '@/theme/tokens';

import { bottomNavigationHeight } from './constants';
import { isActiveRoute, navigationItems } from './items';

export function BottomNavigation() {
  const pathname = usePathname();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.shell, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
      <View style={styles.bar}>
        {navigationItems.map((item) => {
          const active = isActiveRoute(pathname, item.href);
          return (
            <Link key={item.label} href={item.href as Href} asChild>
              <Pressable style={({ pressed }) => [styles.item, active && styles.activeItem, pressed && styles.pressed]}>
                <Text style={[styles.icon, active && styles.activeText]}>{item.icon}</Text>
                <Text style={[styles.label, active && styles.activeText]}>{item.label}</Text>
              </Pressable>
            </Link>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
    borderRadius: 26,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.xs,
    height: bottomNavigationHeight,
    padding: spacing.sm,
    shadowColor: '#000',
    shadowOffset: { height: 8, width: 0 },
    shadowOpacity: 0.28,
    shadowRadius: 16,
  },
  icon: {
    color: colors.muted,
    fontSize: 18,
    fontWeight: '900',
    lineHeight: 20,
  },
  item: {
    alignItems: 'center',
    borderColor: 'transparent',
    borderRadius: 18,
    borderWidth: 1,
    flex: 1,
    gap: 2,
    justifyContent: 'center',
    minHeight: 58,
  },
  label: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
  },
  pressed: {
    opacity: 0.78,
  },
  shell: {
    bottom: 0,
    left: 0,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    position: 'absolute',
    right: 0,
  },
});
