import { useLocalSearchParams, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, TaskEvent, TaskSummary, WorkThreadSummary } from '@/api/client';
import { ExpandableDetails } from '@/components/ExpandableDetails';
import { approvalDecisionLabel, latestApprovalAudit } from '@/features/tasks/approval-audit';
import { MetricCard } from '@/components/MetricCard';
import { MetadataRow } from '@/components/MetadataRow';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { useSettingsStore } from '@/state/settings';
import { useDataStore } from '@/state/data-store';
import { colors, spacing } from '@/theme/tokens';

export default function TaskDetailScreen() {
  const { taskId } = useLocalSearchParams<{ taskId: string }>();
  const router = useRouter();
  const { apiUrl, apiToken } = useSettingsStore();
  const offline = useDataStore((state) => state.offline);
  const stale = useDataStore((state) => state.stale);
  const insets = useSafeAreaInsets();
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [thread, setThread] = useState<WorkThreadSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cacheNotice, setCacheNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionPending, setActionPending] = useState(false);
  const [guidance, setGuidance] = useState('');
  const [editingRetry, setEditingRetry] = useState(false);
  const [continuationMode, setContinuationMode] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

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
        const threadResult = await apiFetch<WorkThreadSummary>(apiUrl, apiToken, `/work-threads/${taskResult.root_task_id || taskResult.task_id}`);
        await writeCache(AsyncStorage, `tasks:${taskId}`, { events: eventResult, task: taskResult });
        if (mounted) {
          setTask(taskResult);
          setEvents(eventResult);
          setThread(threadResult);
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

  async function refreshTaskCache(updated: TaskSummary) {
    if (!taskId) return;
    setTask(updated);
    const eventResult = await apiFetch<TaskEvent[]>(apiUrl, apiToken, `/tasks/${taskId}/events`);
    setEvents(eventResult);
    await writeCache(AsyncStorage, `tasks:${taskId}`, { events: eventResult, task: updated });
  }

  async function runTaskAction(path: string, failureMessage: string) {
    if (offline || stale) { setError('Reconnect before changing task state.'); return; }
    try {
      setActionPending(true);
      setError(null);
      const updated = await apiFetch<TaskSummary>(apiUrl, apiToken, path, { method: 'POST' });
      await refreshTaskCache(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : failureMessage);
    } finally {
      setActionPending(false);
    }
  }

  async function submitContinuation(newSession: boolean) {
    if (!taskId || !guidance.trim()) return;
    try {
      setActionPending(true);
      const next = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}/continue`, {
        method: 'POST',
        body: JSON.stringify({ prompt: guidance.trim(), requires_approval: false, new_session: newSession, relation: 'continuation' }),
      });
      router.replace(`/tasks/${next.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to continue task');
    } finally {
      setActionPending(false);
    }
  }

  async function submitEditedRetry() {
    if (!taskId || !guidance.trim()) return;
    try {
      setActionPending(true);
      const next = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${taskId}/continue`, {
        method: 'POST',
        body: JSON.stringify({ prompt: guidance.trim(), new_session: !continuationMode, relation: continuationMode ? 'continuation' : 'edited_retry' }),
      });
      router.replace(`/tasks/${next.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit edited retry');
    } finally {
      setActionPending(false);
    }
  }

  async function retryUnchanged() {
    if (!task) return;
    if (offline || stale) { setError('Reconnect before changing task state.'); return; }
    try {
      setActionPending(true); setError(null);
      const next = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${task.task_id}/retry`, { method: 'POST' });
      router.replace(`/tasks/${next.task_id}`);
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to retry task'); }
    finally { setActionPending(false); }
  }

  function confirmArchive() {
    if (!task) return;
    const restoring = Boolean(task.archived_at);
    Alert.alert(restoring ? 'Restore task?' : 'Remove from inbox?', restoring ? 'This task will return to your task lists.' : 'The task and its event history will be retained in Archived.', [
      { text: 'Cancel', style: 'cancel' },
      { text: restoring ? 'Restore' : 'Remove', style: restoring ? 'default' : 'destructive', onPress: () => void archiveTask(restoring) },
    ]);
  }

  async function archiveTask(restoring: boolean) {
    if (!task || offline || stale) { setError('Reconnect before changing task state.'); return; }
    try {
      setActionPending(true); setError(null);
      const updated = await apiFetch<TaskSummary>(apiUrl, apiToken, `/tasks/${task.task_id}/${restoring ? 'restore' : 'archive'}`, { method: 'POST' });
      if (restoring) { setActionMessage('Task restored to your inbox.'); await refreshTaskCache(updated); }
      else router.replace('/tasks');
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to update task visibility'); }
    finally { setActionPending(false); }
  }

  const canApprove = task?.status === 'awaiting_approval';
  const canRecover = task?.status === 'failed' || task?.status === 'blocked' || task?.status === 'completed';
  const canCancel = task?.status === 'queued' || task?.status === 'running' || task?.status === 'awaiting_approval';
  const canArchive = task && !canCancel && !['awaiting_approval', 'queued', 'running'].includes(task.status);
  const approvalAudit = latestApprovalAudit(events);

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}> 
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {actionMessage ? <Text accessibilityLiveRegion="polite" style={styles.success}>{actionMessage}</Text> : null}
      {task ? (
        <>
          {thread && thread.latest_attempt.task_id !== task.task_id ? (
            <Pressable accessibilityRole="link" onPress={() => router.replace(`/tasks/${thread.latest_attempt.task_id}`)} style={styles.latestBanner}>
              <Text style={styles.latestText}>A newer attempt exists: view latest outcome</Text>
            </Pressable>
          ) : null}
          <MetricCard title={task.title}>
            <View style={styles.statusRow}>
              <StatusPill status={task.status} />
              <Text style={styles.project}>{task.project_id}</Text>
            </View>
            <View style={styles.actions}>
              {canApprove ? (
                <>
                  <Pressable
                    accessibilityRole="button"
                    disabled={actionPending}
                    onPress={() => runTaskAction(`/tasks/${taskId}/approve`, 'Failed to approve task')}
                    style={[styles.button, actionPending && styles.disabledButton]}
                    testID="task-approve"
                  >
                    <Text style={styles.buttonText}>Approve</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    disabled={actionPending}
                    onPress={() => runTaskAction(`/tasks/${taskId}/reject`, 'Failed to reject task')}
                    style={[styles.button, styles.cancelButton, actionPending && styles.disabledButton]}
                    testID="task-reject"
                  >
                    <Text style={styles.buttonText}>Reject</Text>
                  </Pressable>
                </>
              ) : null}
              {canCancel ? (
                <Pressable
                  accessibilityRole="button"
                  disabled={actionPending}
                  onPress={() => runTaskAction(`/tasks/${taskId}/cancel`, 'Failed to cancel task')}
                  style={[styles.button, styles.cancelButton, actionPending && styles.disabledButton]}
                  testID="task-cancel"
                >
                  <Text style={styles.buttonText}>Cancel</Text>
                </Pressable>
              ) : null}
              {canRecover ? (
                <>
                  <Pressable accessibilityRole="button" disabled={actionPending} onPress={() => void retryUnchanged()} style={[styles.button, actionPending && styles.disabledButton]} testID="task-retry"><Text style={styles.buttonText}>Retry unchanged</Text></Pressable>
                  <Pressable
                    accessibilityRole="button"
                    disabled={actionPending}
                    onPress={() => { setContinuationMode(false); setEditingRetry(true); setGuidance(task.prompt); }}
                    style={[styles.button, actionPending && styles.disabledButton]}
                    testID="task-edit-retry"
                  >
                    <Text style={styles.buttonText}>Edit and retry</Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    disabled={actionPending}
                    onPress={() => { setContinuationMode(true); setGuidance(''); setEditingRetry(true); }}
                    style={[styles.button, actionPending && styles.disabledButton]}
                    testID="task-continue"
                  >
                    <Text style={styles.buttonText}>Continue session</Text>
                  </Pressable>
                </>
              ) : null}
              {canArchive ? <Pressable accessibilityRole="button" disabled={actionPending || offline || stale} onPress={confirmArchive} style={[styles.archiveButton, (actionPending || offline || stale) && styles.disabledButton]} testID="task-archive"><Text style={styles.archiveButtonText}>{task.archived_at ? 'Restore to inbox' : 'Remove from inbox'}</Text></Pressable> : null}
            </View>
            {approvalAudit ? <View style={styles.approvalAudit}>
              <Text style={styles.approvalHeading}>Approval audit · {approvalDecisionLabel(approvalAudit.status)}</Text>
              <MetadataRow label="Actor" value={approvalAudit.actor} />
              <MetadataRow label="Device" value={approvalAudit.deviceId} />
              <MetadataRow label="Reason" value={approvalAudit.reason} />
              <MetadataRow label="Recorded" value={approvalAudit.createdAt} />
            </View> : null}
          </MetricCard>

          <ExpandableDetails label="Task context">
            <Text style={styles.bodyText}>{task.prompt}</Text>
            <MetadataRow label="Relation" value={task.relation || 'original'} />
            <MetadataRow label="Execution folder" value={task.execution_folder} />
            <MetadataRow label="Session" value={task.session_id} />
          </ExpandableDetails>

          {editingRetry ? (
            <MetricCard title={continuationMode ? 'Continue Hermes session' : 'Edit before retry'} subtitle="The original task remains unchanged; this creates a linked task.">
              <TextInput accessibilityLabel="Retry guidance" accessibilityHint="Add guidance or revise the instruction" multiline onChangeText={setGuidance} placeholder="Add guidance or revise the instruction..." placeholderTextColor={colors.muted} style={styles.guidanceInput} value={guidance} />
              <Pressable disabled={actionPending || !guidance.trim()} onPress={submitEditedRetry} style={[styles.button, (!guidance.trim() || actionPending) && styles.disabledButton]} testID="task-submit-edited-retry"><Text style={styles.buttonText}>{continuationMode ? 'Send guidance' : 'Submit edited retry'}</Text></Pressable>
            </MetricCard>
          ) : null}

          {task.result_summary ? (
            <MetricCard title="Result">
              <Text style={styles.bodyText}>{task.result_summary}</Text>
            </MetricCard>
          ) : null}

          {task.blocker_message ? <MetricCard title="Hermes needs attention" subtitle={task.blocker_category || 'blocked'}><Text numberOfLines={3} style={styles.error}>{task.blocker_message}</Text><Text style={styles.muted}>{task.blocker_retryable ? 'Check the environment, then continue or retry.' : 'Review the task before deciding what to do next.'}</Text></MetricCard> : null}

          {task.error ? <ExpandableDetails label="Technical error"><Text style={styles.error}>{task.error}</Text></ExpandableDetails> : null}

          <ExpandableDetails initiallyExpanded={task.status === 'running'} label={`Progress log · ${task.progress_log.length}`}>
            {task.progress_log.length === 0 ? <Text style={styles.muted}>No progress messages yet.</Text> : task.progress_log.map((line, index) => <Text key={`${line}-${index}`} style={styles.logLine}>{line}</Text>)}
          </ExpandableDetails>

          <ExpandableDetails label={`Event timeline · ${events.length}`}>
            {events.length === 0 ? <Text style={styles.muted}>No events recorded yet.</Text> : events.map((event, index) => <View key={`${event.event_type}-${event.created_at}-${index}`} style={styles.eventRow}><Text style={styles.eventType}>{event.event_type}</Text>{event.message ? <Text style={styles.eventMessage}>{event.message}</Text> : null}</View>)}
          </ExpandableDetails>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  approvalAudit: { borderTopColor: colors.border, borderTopWidth: 1, gap: spacing.xs, marginTop: spacing.md, paddingTop: spacing.md },
  approvalHeading: { color: colors.text, fontSize: 14, fontWeight: '800' },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  archiveButton: { borderColor: colors.danger, borderRadius: 12, borderWidth: 1, minWidth: 132, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  archiveButtonText: { color: colors.danger, fontSize: 15, fontWeight: '800', textAlign: 'center' },
  bodyText: {
    color: colors.text,
    fontSize: 15,
    lineHeight: 22,
  },
  button: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 12,
    flexGrow: 1,
    minWidth: 96,
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
  guidanceInput: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    color: colors.text,
    minHeight: 120,
    padding: spacing.md,
    textAlignVertical: 'top',
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
  latestBanner: { backgroundColor: colors.primarySoft, borderColor: colors.primary, borderRadius: 12, borderWidth: 1, padding: spacing.md },
  latestText: { color: colors.text, fontWeight: '800' },
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
  success: { color: colors.success, fontWeight: '800' },
});
