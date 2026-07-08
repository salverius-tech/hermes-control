import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Link } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, TaskSummary } from '@/api/client';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { StatusPill } from '@/components/StatusPill';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function TasksScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cacheNotice, setCacheNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadTasks() {
      try {
        setLoading(true);
        setCacheNotice(null);
        const result = await apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks');
        await writeCache(AsyncStorage, 'tasks:list', result);
        if (mounted) setTasks(result);
      } catch (err) {
        const cached = await readCache<TaskSummary[]>(AsyncStorage, 'tasks:list');
        if (mounted && cached) {
          setTasks(cached);
          setCacheNotice('Showing cached tasks while the API is unavailable.');
        }
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load tasks');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (apiToken) void loadTasks();
    else setLoading(false);
    return () => {
      mounted = false;
    };
  }, [apiToken, apiUrl]);

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {!apiToken ? <Text style={styles.muted}>Configure your API token in Settings.</Text> : null}
      {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {tasks.length === 0 && !loading ? <Text style={styles.muted}>No tasks yet.</Text> : null}
      {tasks.map((task) => (
        <MetricCard key={task.task_id} title={task.title} subtitle={task.prompt}>
          <View style={styles.cardFooter}>
            <StatusPill status={task.status} />
            <Link href={`/tasks/${task.task_id}`} style={styles.project}>Open</Link>
          </View>
        </MetricCard>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  cardFooter: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  error: {
    color: colors.danger,
    fontSize: 15,
  },
  muted: {
    color: colors.muted,
    fontSize: 16,
  },
  project: {
    color: colors.muted,
    fontWeight: '700',
  },
});
