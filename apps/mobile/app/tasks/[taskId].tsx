import { useLocalSearchParams, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, TaskEvent, TaskSummary } from '@/api/client';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function TaskDetailScreen() {
  const { taskId } = useLocalSearchParams<{ taskId: string }>();
  const router = useRouter();
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cacheNotice, setCacheNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function loadTask() {
      try {
        setLoading(true);
        setError(null);
        setCacheNotice(null);
        const [taskResult, eventResult] = await Promise.all([
          apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}`),
          apiFetch<TaskEvent[]>(apiUrl, apiToken, `/tasks/${taskId}/events`),
        ]);
        await writeCache(AsyncStorage, `tasks:${taskId}`, { events: eventResult, task: taskResult });
        if (mounted) {
          setTask(taskResult);
          setEvents(eventResult);
        }
      } catch (err) {
        const cached = await readCache<{ task: TaskSummary; events: TaskEvent[] }>(AsyncStorage, `tasks:${taskId}`);
        if (mounted && cached) {
          setTask(cached.task);
          setEvents(cached.events);
          setCacheNotice('Showing cached task details while the API is unavailable.');
        }
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

  async function cancelTask() {
    if (!taskId) return;
    try {
      setActionPending(true);
      setError(null);
      const canceled = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}/cancel`, { method: 'POST' });
      setTask(canceled);
      const eventResult = await apiFetch<TaskEvent[]>(apiUrl, apiToken, `/tasks/${taskId}/events`);
      setEvents(eventResult);
      await writeCache(AsyncStorage, `tasks:${taskId}`, { events: eventResult, task: canceled });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel task');
    } finally {
      setActionPending(false);
    }
  }

  async function retryTask() {
    if (!taskId) return;
    try {
      setActionPending(true);
      setError(null);
      const retried = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}/retry`, { method: 'POST' });
      router.replace(`/tasks/${retried.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry task');
    } finally {
      setActionPending(false);
    }
  }

  const canCancel = task?.status === 'queued' || task?.status === 'running';

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}> 
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {task ? (
        <>
          <MetricCard title={task.title} subtitle={task.prompt}>
            <View style={styles.statusRow}>
              <StatusPill status={task.status} />
              <Text style={styles.project}>{task.project_id}</Text>
            </View>
            <View style={styles.actions}>
              {canCancel ? (
                <Pressable
                  accessibilityRole="button"
                  disabled={actionPending}
                  onPress={cancelTask}
                  style={[styles.button, styles.cancelButton, actionPending && styles.disabledButton]}
                  testID="task-cancel"
                >
                  <Text style={styles.buttonText}>Cancel</Text>
                </Pressable>
              ) : null}
              <Pressable
                accessibilityRole="button"
                disabled={actionPending}
                onPress={retryTask}
                style={[styles.button, actionPending && styles.disabledButton]}
                testID="task-retry"
              >
                <Text style={styles.buttonText}>Retry</Text>
              </Pressable>
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
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  bodyText: {
    color: colors.text,
    fontSize: 15,
    lineHeight: 22,
  },
  button: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 12,
    flex: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  buttonText: {
    color: colors.background,
    fontSize: 15,
    fontWeight: '800',
  },
  cancelButton: {
    backgroundColor: colors.danger,
  },
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  disabledButton: {
    opacity: 0.6,
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
