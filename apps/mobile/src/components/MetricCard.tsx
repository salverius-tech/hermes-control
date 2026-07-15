import { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

type Props = {
  title: string;
  subtitle?: string;
  children?: ReactNode;
};

export function MetricCard({ title, subtitle, children }: Props) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
      {children ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  body: {
    marginTop: spacing.md,
  },
  card: {
    backgroundColor: colors.elevated,
    borderRadius: 18,
    padding: spacing.md,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 18,
    marginTop: spacing.xs,
  },
  title: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '900',
  },
});
