import { Feather } from '@expo/vector-icons';
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
            <View key={item.label} style={styles.slot}>
              <Link href={item.href as Href} replace={item.replace} asChild>
                <Pressable
                  testID={`nav-${item.label.toLowerCase()}`}
                  style={({ pressed }) => [styles.item, active && styles.activeItem, pressed && styles.pressed]}
                >
                  <Feather color={active ? colors.text : colors.muted} name={item.iconName} size={28} />
                  <Text style={[styles.label, active && styles.activeText]}>{item.label}</Text>
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
  item: {
    alignItems: 'center',
    borderColor: 'transparent',
    borderRadius: 18,
    borderWidth: 1,
    gap: 2,
    height: '100%',
    justifyContent: 'center',
    width: '100%',
  },
  label: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: '800',
    textAlign: 'center',
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
  slot: {
    flex: 1,
    height: '100%',
    paddingHorizontal: spacing.xs,
  },
});
