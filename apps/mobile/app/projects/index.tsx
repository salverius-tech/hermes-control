import AsyncStorage from '@react-native-async-storage/async-storage';
import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { readCache, writeCache } from '@/api/cache';
import { apiFetch, ProjectSummary } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { MetadataRow } from '@/components/MetadataRow';
import { SectionHeader } from '@/components/SectionHeader';
import { StatusPill } from '@/components/StatusPill';
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
  const loadProjects = async (refreshing = false) => {
    try { if (!refreshing) setLoading(true); setCacheNotice(null); setError(null); const result = await apiFetch<ProjectSummary[]>(apiUrl, apiToken, '/projects'); await writeCache(AsyncStorage, 'projects:list', result); setProjects(result); }
    catch (err) { const cached = await readCache<ProjectSummary[]>(AsyncStorage, 'projects:list'); if (cached) { setProjects(cached); setCacheNotice('Showing cached projects.'); } setError(err instanceof Error ? err.message : 'Failed to load projects'); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (apiToken) void loadProjects(); else setLoading(false); }, [apiToken, apiUrl]);

  return <ScrollView refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void loadProjects(true)} refreshing={loading} />} contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
    <View style={styles.intro}><Text style={styles.heading}>Projects</Text><Text style={styles.muted}>Choose a workspace to review threads or start the next task.</Text></View>
    <View style={styles.headerRow}><SectionHeader count={projects.length} title="Workspaces" /><Link href="/projects/manage" asChild><Pressable accessibilityRole="button"><Text style={styles.link}>New project</Text></Pressable></Link></View>
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {cacheNotice ? <Text style={styles.muted}>{cacheNotice}</Text> : null}
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {!loading && projects.length === 0 ? <EmptyState body="Create a project or configure the API in Settings." title="No projects yet" /> : null}
    {projects.map((project) => <Link key={project.project_id} href={`/projects/${encodeURIComponent(project.project_id)}`} asChild><Pressable style={({ pressed }) => [styles.card, pressed && styles.pressed]}><View style={styles.cardTop}><View style={styles.copy}><Text numberOfLines={1} style={styles.title}>{project.name}</Text><Text style={styles.status}>{project.archived ? 'Archived workspace' : 'Active workspace'}</Text></View><StatusPill status={project.archived ? 'offline' : project.running_count > 0 ? 'running' : 'idle'} /></View><View style={styles.metadata}><MetadataRow label="Attention" value={`${project.failed_count} failed`} /><MetadataRow label="Active" value={`${project.running_count + project.queued_count} tasks`} /><MetadataRow label="Completed" value={`${project.completed_count}`} /></View></Pressable></Link>)}
  </ScrollView>;
}

const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, borderRadius: 18, gap: spacing.md, padding: spacing.md }, cardTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' }, container: { gap: spacing.lg, padding: spacing.lg }, copy: { flex: 1, gap: spacing.xs }, error: { color: colors.danger, fontSize: 14 }, heading: { color: colors.text, fontSize: 30, fontWeight: '900' }, headerRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' }, link: { color: colors.primary, fontSize: 14, fontWeight: '800' }, metadata: { borderTopColor: colors.border, borderTopWidth: 1, gap: spacing.xs, paddingTop: spacing.sm }, muted: { color: colors.muted, fontSize: 14, lineHeight: 20 }, pressed: { opacity: 0.75 }, status: { color: colors.muted, fontSize: 12 }, title: { color: colors.text, fontSize: 17, fontWeight: '800' }, intro: { gap: spacing.xs } });
