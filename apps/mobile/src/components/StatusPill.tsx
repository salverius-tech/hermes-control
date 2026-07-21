import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

export type StatusKind = 'awaiting_approval' | 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | 'rejected' | 'blocked' | 'idle' | 'busy' | 'offline' | 'already_registered' | 'ready' | 'missing_repository' | 'conflict';

const statusColor: Record<StatusKind, string> = {
  awaiting_approval: colors.warning,
  queued: colors.warning,
  running: colors.primary,
  completed: colors.success,
  failed: colors.danger,
  canceled: colors.muted,
  rejected: colors.danger,
  blocked: colors.warning,
  idle: colors.success,
  busy: colors.primary,
  offline: colors.muted,
  already_registered: colors.success,
  ready: colors.primary,
  missing_repository: colors.warning,
  conflict: colors.danger,
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
