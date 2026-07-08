import { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, ProjectSummary } from '@/api/client';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function ProjectsScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cacheNotice, setCacheNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function loadProjects() {
      try {
        setLoading(true);
        setCacheNotice(null);
        const result = await apiFetch<ProjectSummary[]>(apiUrl, apiToken, '/projects');
        await writeCache(AsyncStorage, 'projects:list', result);
        if (mounted) setProjects(result);
      } catch (err) {
        const cached = await readCache<ProjectSummary[]>(AsyncStorage, 'projects:list');
        if (mounted && cached) {
          setProjects(cached);
          setCacheNotice('Showing cached projects while the API is unavailable.');
        }
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load projects');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (apiToken) void loadProjects();
    else setLoading(false);
    return () => {
      mounted = false;
    };
  }, [apiToken, apiUrl]);

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {projects.map((project) => (
        <MetricCard key={project.project_id} title={project.name} subtitle={project.project_id}>
          <Text style={styles.counts}>
            {project.running_count} running · {project.queued_count} queued · {project.completed_count} done · {project.failed_count} failed
          </Text>
        </MetricCard>
      ))}
      {!loading && projects.length === 0 ? <Text style={styles.muted}>No projects loaded.</Text> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  counts: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '700',
  },
  error: {
    color: colors.danger,
    fontSize: 15,
  },
  muted: {
    color: colors.muted,
    fontSize: 16,
  },
});
