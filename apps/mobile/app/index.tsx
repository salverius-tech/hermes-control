import AsyncStorage from '@react-native-async-storage/async-storage';
import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, AgentStatus, Diagnostics, ProjectSummary, TaskSummary } from '@/api/client';
import { readCache, writeCache } from '@/api/cache';
import { MetricCard } from '@/components/MetricCard';
import { StatusPill } from '@/components/StatusPill';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function DashboardScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        setLoading(true);
        const [taskResult, projectResult, agentResult, diagnosticResult] = await Promise.all([
          apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks'),
          apiFetch<ProjectSummary[]>(apiUrl, apiToken, '/projects'),
          apiFetch<AgentStatus[]>(apiUrl, apiToken, '/agents'),
          apiFetch<Diagnostics>(apiUrl, apiToken, '/diagnostics'),
        ]);
        if (!mounted) return;
        setTasks(taskResult);
        setProjects(projectResult);
        setAgents(agentResult);
        setDiagnostics(diagnosticResult);
        setOffline(false);
        await Promise.all([
          writeCache(AsyncStorage, 'dashboard:tasks', taskResult),
          writeCache(AsyncStorage, 'dashboard:projects', projectResult),
          writeCache(AsyncStorage, 'dashboard:agents', agentResult),
        ]);
      } catch {
        const [cachedTasks, cachedProjects, cachedAgents] = await Promise.all([
          readCache<TaskSummary[]>(AsyncStorage, 'dashboard:tasks'),
          readCache<ProjectSummary[]>(AsyncStorage, 'dashboard:projects'),
          readCache<AgentStatus[]>(AsyncStorage, 'dashboard:agents'),
        ]);
        if (!mounted) return;
        if (cachedTasks) setTasks(cachedTasks);
        if (cachedProjects) setProjects(cachedProjects);
        if (cachedAgents) setAgents(cachedAgents);
        setOffline(true);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (apiToken) void load();
    else setLoading(false);
    return () => { mounted = false; };
  }, [apiToken, apiUrl]);

  const attention = tasks.filter((task) => task.status === 'awaiting_approval' || task.status === 'failed' || task.status === 'blocked');
  const running = tasks.filter((task) => task.status === 'running');
  const agent = agents[0];

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]} showsVerticalScrollIndicator={false}>
      <View style={styles.hero}>
        <Text style={styles.eyebrow}>HERMES WORK INBOX</Text>
        <Text style={styles.title}>What needs your attention?</Text>
        <Text style={styles.subtitle}>Open a project to continue work, review a blocked task, or start a new instruction in the right workspace.</Text>
        {offline ? <Text style={styles.warning}>Showing cached state. The Control API could not be reached.</Text> : null}
      </View>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      <View style={styles.grid}>
        <MetricCard title="Needs attention" subtitle="Approval, failure, or guidance"><Text style={[styles.metric, attention.length > 0 && styles.warningText]}>{attention.length}</Text></MetricCard>
        <MetricCard title="Running tasks" subtitle="Hermes is working"><Text style={styles.metric}>{running.length}</Text></MetricCard>
      </View>
      <MetricCard title="Hermes agent" subtitle={diagnostics?.execution_mode ? `Execution: ${diagnostics.execution_mode}` : 'Connection not configured'}>
        <StatusPill status={agent?.status || (offline ? 'offline' : 'idle')} />
      </MetricCard>
      <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Projects</Text><Link href="/projects" asChild><Pressable><Text style={styles.link}>View all</Text></Pressable></Link></View>
      {projects.slice(0, 4).map((project) => <Link key={project.project_id} href={`/projects/${encodeURIComponent(project.project_id)}`} asChild><Pressable style={styles.project}><View><Text style={styles.projectName}>{project.name}</Text><Text style={styles.muted}>{project.primary_folder || project.project_id}</Text></View><Text style={styles.projectCount}>{project.running_count + project.queued_count}</Text></Pressable></Link>)}
      {!loading && projects.length === 0 ? <Text style={styles.muted}>Configure the API in Settings to load Hermes projects.</Text> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { gap: spacing.lg, padding: spacing.lg },
  eyebrow: { color: colors.primary, fontSize: 12, fontWeight: '900', letterSpacing: 2 },
  grid: { flexDirection: 'row', gap: spacing.md },
  hero: { backgroundColor: colors.elevated, borderColor: colors.border, borderRadius: 32, borderWidth: 1, gap: spacing.md, padding: spacing.xl },
  link: { color: colors.primary, fontSize: 15, fontWeight: '800' },
  metric: { color: colors.text, fontSize: 42, fontWeight: '900' },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  project: { alignItems: 'center', backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, flexDirection: 'row', justifyContent: 'space-between', padding: spacing.md },
  projectCount: { color: colors.text, fontSize: 20, fontWeight: '900' },
  projectName: { color: colors.text, fontSize: 17, fontWeight: '800' },
  sectionHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  sectionTitle: { color: colors.text, fontSize: 22, fontWeight: '900' },
  subtitle: { color: colors.muted, fontSize: 16, lineHeight: 24 },
  title: { color: colors.text, fontSize: 34, fontWeight: '900', letterSpacing: -1 },
  warning: { color: colors.warning, fontSize: 14, fontWeight: '800', lineHeight: 20 },
  warningText: { color: colors.warning },
});
