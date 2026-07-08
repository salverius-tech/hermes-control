import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

export function HeaderSettingsButton() {
  return (
    <Link href="/settings" asChild>
      <Pressable accessibilityLabel="Settings" accessibilityRole="button" hitSlop={10} style={styles.button} testID="header-settings">
        <Text style={styles.icon}>⚙</Text>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    borderRadius: 18,
    height: 36,
    justifyContent: 'center',
    marginRight: spacing.xs,
    width: 36,
  },
  icon: {
    color: colors.text,
    fontSize: 24,
    fontWeight: '900',
    lineHeight: 28,
  },
});
