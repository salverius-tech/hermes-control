import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

export type StatusKind = 'queued' | 'running' | 'completed' | 'failed' | 'idle' | 'offline';

const statusColor: Record<StatusKind, string> = {
  queued: colors.warning,
  running: colors.primary,
  completed: colors.success,
  failed: colors.danger,
  idle: colors.success,
  offline: colors.muted,
};

type Props = {
  status: StatusKind;
};

export function StatusPill({ status }: Props) {
  return (
    <View style={[styles.pill, { borderColor: statusColor[status] }]}>
      <View style={[styles.dot, { backgroundColor: statusColor[status] }]} />
      <Text style={styles.text}>{status.toUpperCase()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  dot: {
    borderRadius: 999,
    height: 8,
    width: 8,
  },
  text: {
    color: colors.text,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
});
