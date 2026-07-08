import { Link } from 'expo-router';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { colors, spacing } from '@/theme/tokens';

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();

  return (
    <ScrollView
      contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.hero}>
        <Text style={styles.eyebrow}>LOCAL HERMES</Text>
        <Text style={styles.title}>Mobile command center</Text>
        <Text style={styles.subtitle}>
          Monitor projects, review running tasks, and start new Hermes work from text or voice.
        </Text>
      </View>

      <View style={styles.grid}>
        <MetricCard title="Agent status" subtitle="Default local Hermes agent">
          <StatusPill status="offline" />
        </MetricCard>
        <MetricCard title="Running tasks" subtitle="No active task stream yet">
          <Text style={styles.metric}>0</Text>
        </MetricCard>
      </View>

      <View style={styles.actions}>
        <Link href="/new-task" style={styles.primaryAction}>Start new task</Link>
        <Link href="/tasks" style={styles.secondaryAction}>View tasks</Link>
        <Link href="/settings" style={styles.secondaryAction}>Configure API</Link>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  actions: {
    gap: spacing.md,
  },
  container: {
    gap: spacing.lg,
    padding: spacing.lg,
  },
  eyebrow: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 2,
  },
  grid: {
    gap: spacing.md,
  },
  hero: {
    backgroundColor: colors.elevated,
    borderColor: colors.border,
    borderRadius: 32,
    borderWidth: 1,
    gap: spacing.md,
    padding: spacing.xl,
  },
  metric: {
    color: colors.text,
    fontSize: 42,
    fontWeight: '900',
  },
  primaryAction: {
    backgroundColor: colors.primary,
    borderRadius: 18,
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
    overflow: 'hidden',
    padding: spacing.lg,
    textAlign: 'center',
  },
  secondaryAction: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
    overflow: 'hidden',
    padding: spacing.md,
    textAlign: 'center',
  },
  subtitle: {
    color: colors.muted,
    fontSize: 16,
    lineHeight: 24,
  },
  title: {
    color: colors.text,
    fontSize: 38,
    fontWeight: '900',
    letterSpacing: -1,
  },
});
