import AsyncStorage from '@react-native-async-storage/async-storage';
import { Link } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { filterActivityThreads } from '@/features/tasks/activity-search';
import { taskFilters, type TaskFilter } from '@/features/tasks/filters';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { useDataStore } from '@/state/data-store';
import { removeQueuedTask, retryQueuedTask } from '@/features/tasks/offline-queue';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function TasksScreen() {
  const { apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const workThreads = useDataStore((state) => state.workThreads);
  const queuedTasks = useDataStore((state) => state.queuedTasks);
  const refresh = useDataStore((state) => state.refresh);
  const offline = useDataStore((state) => state.offline);
  const [filter, setFilter] = useState<TaskFilter>('inbox');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');

  async function loadTasks(showSpinner = false) {
    if (showSpinner) setRefreshing(true);
    await refresh();
    setLoading(false);
    setRefreshing(false);
  }

  useEffect(() => {
    if (!apiToken) { setLoading(false); return; }
    void loadTasks();
    const interval = setInterval(() => void loadTasks(), 30000);
    return () => clearInterval(interval);
  }, [apiToken, refresh]);

  const visibleThreads = useMemo(() => filterActivityThreads(workThreads, filter, query), [filter, query, workThreads]);

  return (
    <ScrollView refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void loadTasks(true)} refreshing={refreshing} />} contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      <Text style={styles.heading}>Tasks</Text>
      <Text style={styles.muted}>Inbox shows work that needs attention or is still active.</Text>
      <TextInput accessibilityLabel="Search activity" onChangeText={setQuery} placeholder="Search activity, history, or projects" placeholderTextColor={colors.muted} style={styles.search} testID="activity-search" value={query} />
      <ScrollView contentContainerStyle={styles.filters} horizontal showsHorizontalScrollIndicator={false}>
        {taskFilters.map((item) => <Pressable accessibilityRole="button" accessibilityState={{ selected: filter === item.value }} key={item.value} onPress={() => setFilter(item.value)} style={[styles.filter, filter === item.value && styles.filterSelected]}><Text style={[styles.filterText, filter === item.value && styles.filterTextSelected]}>{item.label}</Text></Pressable>)}
      </ScrollView>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {!apiToken ? <Text style={styles.muted}>Configure your API token in Settings.</Text> : null}
      {offline ? <Text style={styles.muted}>Showing cached tasks while the API is unavailable.</Text> : null}
      {queuedTasks.map((item) => (
        <View key={item.local_id} style={styles.queuedCard} testID={`queued-task-${item.local_id}`}>
          <View style={styles.cardTop}><Text style={styles.title} numberOfLines={2}>{item.request.prompt}</Text><Text style={styles.queueStatus}>{item.state}</Text></View>
          <Text style={styles.meta}>Saved locally · attempt {item.attempts}</Text>
          <View style={styles.queueActions}>
            <Pressable onPress={() => void retryQueuedTask(AsyncStorage, item.local_id).then(refresh)} style={styles.queueButton} testID={`queued-task-retry-${item.local_id}`}><Text style={styles.queueButtonText}>Retry now</Text></Pressable>
            <Pressable onPress={() => void removeQueuedTask(AsyncStorage, item.local_id).then(refresh)} style={styles.queueCancel} testID={`queued-task-discard-${item.local_id}`}><Text style={styles.queueButtonText}>Discard</Text></Pressable>
          </View>
        </View>
      ))}
      {visibleThreads.length === 0 && !loading ? <Text style={styles.muted}>{filter === 'inbox' ? 'No work needs your attention right now.' : 'No tasks in this view.'}</Text> : null}
      {visibleThreads.map((thread) => {
        const task = thread.latest_attempt;
        return (
        <Link key={thread.root_task_id} href={`/tasks/${task.task_id}`} asChild>
          <Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
            <View style={styles.cardTop}><Text style={styles.title} numberOfLines={2}>{task.title}</Text><StatusPill status={task.status} /></View>
            <Text style={styles.prompt} numberOfLines={3}>{task.prompt}</Text>
            <Text style={styles.meta}>{task.project_id} · {thread.attempts.length} attempt{thread.attempts.length === 1 ? '' : 's'} · {new Date(task.updated_at).toLocaleString()}</Text>
          </Pressable>
        </Link>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: spacing.sm, padding: spacing.lg },
  cardTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' },
  container: { gap: spacing.md, padding: spacing.lg },
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
  queueActions: { flexDirection: 'row', gap: spacing.sm },
  queueButton: { backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  queueButtonText: { color: colors.background, fontWeight: '800' },
  queueCancel: { backgroundColor: colors.danger, borderRadius: 10, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  queuedCard: { backgroundColor: colors.elevated, borderColor: colors.warning, borderRadius: 20, borderWidth: 1, gap: spacing.sm, padding: spacing.lg },
  queueStatus: { color: colors.warning, fontWeight: '900', textTransform: 'uppercase' },
  search: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, color: colors.text, padding: spacing.md },
  title: { color: colors.text, flex: 1, fontSize: 17, fontWeight: '800' },
});
