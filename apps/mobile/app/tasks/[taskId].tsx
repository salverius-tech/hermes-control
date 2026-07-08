import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { apiFetch, TaskSummary } from '@/api/client';
import { MetricCard } from '@/components/MetricCard';
import { StatusPill } from '@/components/StatusPill';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function TaskDetailScreen() {
  const { taskId } = useLocalSearchParams<{ taskId: string }>();
  const { apiUrl, apiToken } = useSettingsStore();
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadTask() {
      try {
        setLoading(true);
        const result = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}`);
        if (mounted) setTask(result);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load task');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (taskId && apiToken) void loadTask();
    return () => {
      mounted = false;
    };
  }, [apiToken, apiUrl, taskId]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {task ? (
        <>
          <MetricCard title={task.title} subtitle={task.prompt}>
            <View style={styles.statusRow}>
              <StatusPill status={task.status} />
              <Text style={styles.project}>{task.project_id}</Text>
            </View>
          </MetricCard>
          <MetricCard title="Progress log">
            {task.progress_log.length === 0 ? (
              <Text style={styles.muted}>No progress messages yet.</Text>
            ) : (
              task.progress_log.map((line, index) => (
                <Text key={`${line}-${index}`} style={styles.logLine}>{line}</Text>
              ))
            )}
          </MetricCard>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  error: {
    color: colors.danger,
  },
  logLine: {
    color: colors.text,
    fontFamily: 'Courier',
    lineHeight: 22,
  },
  muted: {
    color: colors.muted,
  },
  project: {
    color: colors.muted,
    fontWeight: '700',
  },
  statusRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
});
