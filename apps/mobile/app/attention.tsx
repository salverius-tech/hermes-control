import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text } from 'react-native';
import { Link } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, TaskSummary } from '@/api/client';
import { StatusPill } from '@/components/StatusPill';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function AttentionScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(showRefresh = false) {
    try { if (showRefresh) setRefreshing(true); setError(null); setTasks(await apiFetch<TaskSummary[]>(apiUrl, apiToken, '/attention')); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to load attention items'); }
    finally { setLoading(false); setRefreshing(false); }
  }

  useEffect(() => { if (apiToken) void load(); else setLoading(false); }, [apiToken, apiUrl]);

  return <ScrollView refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void load(true)} refreshing={refreshing} />} contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
    <Text style={styles.title}>Needs attention</Text>
    <Text style={styles.muted}>Review approvals, blockers, and failures when you check in with Hermes.</Text>
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {!loading && !tasks.length ? <Text style={styles.muted}>Nothing needs your attention.</Text> : null}
    {tasks.map((task) => <Link key={task.task_id} href={`/tasks/${task.task_id}`} asChild><Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]}><Text style={styles.taskTitle}>{task.title}</Text><StatusPill status={task.status} /><Text style={styles.project}>{task.project_id} · {task.blocker_category || task.error || 'Approval required'}</Text></Pressable></Link>)}
  </ScrollView>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: spacing.sm, padding: spacing.lg },
  container: { gap: spacing.md, padding: spacing.lg },
  error: { color: colors.danger },
  muted: { color: colors.muted, fontSize: 15, lineHeight: 21 },
  pressed: { opacity: 0.75 },
  project: { color: colors.muted, fontSize: 13 },
  taskTitle: { color: colors.text, fontSize: 17, fontWeight: '800' },
  title: { color: colors.text, fontSize: 30, fontWeight: '900' },
});
