import AsyncStorage from '@react-native-async-storage/async-storage';
import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, ProjectSummary } from '@/api/client';
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
        setError(null);
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
      <View style={styles.headerRow}><Text style={styles.heading}>Your Hermes workspaces</Text><Link href="/projects/manage" asChild><Pressable><Text style={styles.link}>New project</Text></Pressable></Link></View>
      <Text style={styles.muted}>Select a project to browse its sessions and run the next task in its primary folder.</Text>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {projects.map((project) => (
        <Link key={project.project_id} href={`/projects/${encodeURIComponent(project.project_id)}`} asChild>
          <Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]}>
            <Text style={styles.title}>{project.name}</Text>
            <Text style={styles.id}>{project.project_id}</Text>
            {project.primary_folder ? <Text style={styles.id}>{project.primary_folder}</Text> : null}
            <Text style={styles.counts}>
              {project.running_count} running · {project.queued_count} queued · {project.completed_count} done · {project.failed_count} failed
            </Text>
          </Pressable>
        </Link>
      ))}
      {!loading && projects.length === 0 ? <Text style={styles.muted}>No projects loaded.</Text> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 22, borderWidth: 1, gap: spacing.xs, padding: spacing.lg },
  container: { gap: spacing.md, padding: spacing.lg },
  counts: { color: colors.text, fontSize: 15, fontWeight: '700', marginTop: spacing.sm },
  error: { color: colors.danger, fontSize: 15 },
  headerRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  heading: { color: colors.text, fontSize: 24, fontWeight: '900' },
  link: { color: colors.primary, fontSize: 15, fontWeight: '800' },
  id: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  muted: { color: colors.muted, fontSize: 15, lineHeight: 21 },
  pressed: { opacity: 0.78 },
  title: { color: colors.text, fontSize: 19, fontWeight: '800' },
});
