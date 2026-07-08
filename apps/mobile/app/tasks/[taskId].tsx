import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, TaskEvent, TaskSummary } from '@/api/client';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function TaskDetailScreen() {
  const { taskId } = useLocalSearchParams<{ taskId: string }>();
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadTask() {
      try {
        setLoading(true);
        setError(null);
        const [taskResult, eventResult] = await Promise.all([
          apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}`),
          apiFetch<TaskEvent[]>(apiUrl, apiToken, `/tasks/${taskId}/events`),
        ]);
        if (mounted) {
          setTask(taskResult);
          setEvents(eventResult);
        }
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
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}> 
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

          {task.result_summary ? (
            <MetricCard title="Result">
              <Text style={styles.bodyText}>{task.result_summary}</Text>
            </MetricCard>
          ) : null}

          {task.error ? (
            <MetricCard title="Error">
              <Text style={styles.error}>{task.error}</Text>
            </MetricCard>
          ) : null}

          <MetricCard title="Progress log">
            {task.progress_log.length === 0 ? (
              <Text style={styles.muted}>No progress messages yet.</Text>
            ) : (
              task.progress_log.map((line, index) => (
                <Text key={`${line}-${index}`} style={styles.logLine}>{line}</Text>
              ))
            )}
          </MetricCard>

          <MetricCard title="Event timeline">
            {events.length === 0 ? (
              <Text style={styles.muted}>No events recorded yet.</Text>
            ) : (
              events.map((event, index) => (
                <View key={`${event.event_type}-${event.created_at}-${index}`} style={styles.eventRow}>
                  <Text style={styles.eventType}>{event.event_type}</Text>
                  {event.message ? <Text style={styles.eventMessage}>{event.message}</Text> : null}
                </View>
              ))
            )}
          </MetricCard>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  bodyText: {
    color: colors.text,
    fontSize: 15,
    lineHeight: 22,
  },
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  error: {
    color: colors.danger,
  },
  eventMessage: {
    color: colors.muted,
    fontSize: 13,
    lineHeight: 19,
  },
  eventRow: {
    borderBottomColor: colors.border,
    borderBottomWidth: 1,
    gap: spacing.xs,
    paddingVertical: spacing.sm,
  },
  eventType: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
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
