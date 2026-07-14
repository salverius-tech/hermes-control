import AsyncStorage from '@react-native-async-storage/async-storage';
import { Link } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, TaskStatus, TaskSummary } from '@/api/client';
import { createEventsSocket, parseLiveEvent } from '@/api/events';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

const filters: Array<{ label: string; value: TaskStatus | 'all' | 'attention' }> = [
  { label: 'All', value: 'all' },
  { label: 'Attention', value: 'attention' },
  { label: 'Running', value: 'running' },
  { label: 'Done', value: 'completed' },
  { label: 'Failed', value: 'failed' },
];

export default function TasksScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [filter, setFilter] = useState<(typeof filters)[number]['value']>('all');
  const [error, setError] = useState<string | null>(null);
  const [cacheNotice, setCacheNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function loadTasks(showSpinner = false) {
    try {
      if (showSpinner) setRefreshing(true);
      setError(null);
      const result = await apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks');
      await writeCache(AsyncStorage, 'tasks:list', result);
      setTasks(result);
      setCacheNotice(null);
    } catch (err) {
      const cached = await readCache<TaskSummary[]>(AsyncStorage, 'tasks:list');
      if (cached) {
        setTasks(cached);
        setCacheNotice('Showing cached tasks while the API is unavailable.');
      }
      setError(err instanceof Error ? err.message : 'Failed to load tasks');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    if (!apiToken) { setLoading(false); return; }
    void loadTasks();
    const interval = setInterval(() => void loadTasks(), 15000);
    const socket = createEventsSocket(apiUrl, apiToken);
    socket.onmessage = (message) => {
      const event = parseLiveEvent(message.data);
      if (!event) return;
      if (event.type === 'snapshot') setTasks(event.tasks);
      if (event.type === 'task.created' || event.type === 'task.updated') {
        setTasks((current) => [event.task, ...current.filter((task) => task.task_id !== event.task.task_id)]);
      }
    };
    socket.onerror = () => socket.close();
    return () => { clearInterval(interval); socket.close(); };
  }, [apiToken, apiUrl]);

  const visibleTasks = useMemo(() => tasks.filter((task) => {
    if (filter === 'all') return true;
    if (filter === 'attention') return task.status === 'awaiting_approval' || task.status === 'failed' || task.status === 'blocked';
    return task.status === filter;
  }), [filter, tasks]);

  return (
    <ScrollView refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void loadTasks(true)} refreshing={refreshing} />} contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      <Text style={styles.heading}>Work inbox</Text>
      <Text style={styles.muted}>Tasks refresh automatically while this screen is open.</Text>
      <ScrollView contentContainerStyle={styles.filters} horizontal showsHorizontalScrollIndicator={false}>
        {filters.map((item) => <Pressable key={item.value} onPress={() => setFilter(item.value)} style={[styles.filter, filter === item.value && styles.filterSelected]}><Text style={[styles.filterText, filter === item.value && styles.filterTextSelected]}>{item.label}</Text></Pressable>)}
      </ScrollView>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {!apiToken ? <Text style={styles.muted}>Configure your API token in Settings.</Text> : null}
      {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {visibleTasks.length === 0 && !loading ? <Text style={styles.muted}>No tasks in this view.</Text> : null}
      {visibleTasks.map((task) => (
        <Link key={task.task_id} href={`/tasks/${task.task_id}`} asChild>
          <Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
            <View style={styles.cardTop}><Text style={styles.title} numberOfLines={2}>{task.title}</Text><StatusPill status={task.status} /></View>
            <Text style={styles.prompt} numberOfLines={3}>{task.prompt}</Text>
            <Text style={styles.meta}>{task.project_id} · {task.relation || 'original'} · {new Date(task.updated_at).toLocaleString()}</Text>
          </Pressable>
        </Link>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: spacing.sm, padding: spacing.lg },
  cardTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' },
  container: { gap: spacing.md, padding: spacing.lg },
  error: { color: colors.danger, fontSize: 15 },
  filter: { borderColor: colors.border, borderRadius: 999, borderWidth: 1, marginRight: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  filterSelected: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  filterText: { color: colors.muted, fontWeight: '800' },
  filterTextSelected: { color: colors.text },
  filters: { paddingVertical: spacing.xs },
  heading: { color: colors.text, fontSize: 28, fontWeight: '900' },
  meta: { color: colors.muted, fontSize: 13 },
  muted: { color: colors.muted, fontSize: 15, lineHeight: 21 },
  pressed: { opacity: 0.75 },
  prompt: { color: colors.muted, fontSize: 15, lineHeight: 21 },
  title: { color: colors.text, flex: 1, fontSize: 17, fontWeight: '800' },
});
