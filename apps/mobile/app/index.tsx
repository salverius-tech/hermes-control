import { Link } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, AgentStatus, Diagnostics, ProjectSummary, TaskSummary } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { MetricCard } from '@/components/MetricCard';
import { MetadataRow } from '@/components/MetadataRow';
import { SectionHeader } from '@/components/SectionHeader';
import { StatusPill } from '@/components/StatusPill';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useDataStore } from '@/state/data-store';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function DashboardScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const websocket = useDataStore((state) => state.websocket);
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
        setTasks(taskResult); setProjects(projectResult); setAgents(agentResult); setDiagnostics(diagnosticResult); setOffline(false);
      } catch {
        if (mounted) setOffline(true);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (apiToken) void load(); else setLoading(false);
    return () => { mounted = false; };
  }, [apiToken, apiUrl]);

  const attention = tasks.filter((task) => ['awaiting_approval', 'failed', 'blocked'].includes(task.status));
  const running = tasks.filter((task) => task.status === 'running' || task.status === 'queued');
  const agent = agents[0];
  const connectionStatus = offline || websocket === 'disconnected' ? 'offline' : websocket === 'connected' ? 'busy' : 'idle';

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]} showsVerticalScrollIndicator={false}>
      <View style={styles.hero}>
        <View style={styles.heroTop}><Text style={styles.eyebrow}>HERMES CONTROL</Text><StatusPill status={connectionStatus} /></View>
        <Text style={styles.title}>Work inbox</Text>
        <Text style={styles.subtitle}>Review what needs a decision, then return to the right project.</Text>
      </View>
      {offline ? <Text style={styles.warning}>Showing the last available state. Reconnect to reconcile.</Text> : null}
      {loading ? <ActivityIndicator color={colors.primary} /> : null}

      <View style={styles.grid}>
        <MetricCard title="Needs attention" subtitle="Approval, blocker, or failure"><Text style={[styles.metric, attention.length > 0 && styles.warningText]}>{attention.length}</Text></MetricCard>
        <MetricCard title="Active work" subtitle="Queued or running"><Text style={styles.metric}>{running.length}</Text></MetricCard>
      </View>

      <MetricCard title="Hermes agent" subtitle={diagnostics?.execution_mode ? `Execution · ${diagnostics.execution_mode}` : 'Connection not configured'}>
        <View style={styles.agentRow}><StatusPill status={agent?.status || (offline ? 'offline' : 'idle')} /><Text style={styles.muted}>{websocket === 'connected' ? 'Live updates on' : 'Live updates off'}</Text></View>
      </MetricCard>

      <View style={styles.section}><SectionHeader actionHref="/attention" actionLabel="View all" count={attention.length} title="Needs attention" />
        {attention.slice(0, 3).map((task) => <TaskRow key={task.task_id} task={task} />)}
        {!loading && attention.length === 0 ? <EmptyState body="Approvals, blockers, and failures will appear here." title="All clear" /> : null}
      </View>

      <View style={styles.section}><SectionHeader actionHref="/tasks" actionLabel="View all" count={running.length} title="Active work" />
        {running.slice(0, 3).map((task) => <TaskRow key={task.task_id} task={task} />)}
        {!loading && running.length === 0 ? <EmptyState body="Start a task from a project when you are ready." title="Nothing running" /> : null}
      </View>

      <View style={styles.section}><SectionHeader actionHref="/projects" actionLabel="View all" count={projects.length} title="Projects" />
        {projects.slice(0, 4).map((project) => <Link key={project.project_id} href={`/projects/${encodeURIComponent(project.project_id)}`} asChild><Pressable style={({ pressed }) => [styles.project, pressed && styles.pressed]}><View style={styles.projectCopy}><Text numberOfLines={1} style={styles.projectName}>{project.name}</Text><MetadataRow label="Active" value={`${project.running_count + project.queued_count} tasks`} /></View><Text style={styles.chevron}>›</Text></Pressable></Link>)}
        {!loading && projects.length === 0 ? <EmptyState body="Configure the API in Settings to load workspaces." title="No projects yet" /> : null}
      </View>
    </ScrollView>
  );
}

function TaskRow({ task }: { task: TaskSummary }) {
  return <Link href={`/tasks/${task.task_id}`} asChild><Pressable style={({ pressed }) => [styles.task, pressed && styles.pressed]}><View style={styles.taskTop}><Text numberOfLines={2} style={styles.taskTitle}>{task.title}</Text><StatusPill status={task.status} /></View><Text numberOfLines={1} style={styles.muted}>{task.project_id} · {task.relation || 'original'}</Text></Pressable></Link>;
}

const styles = StyleSheet.create({
  agentRow: { alignItems: 'center', flexDirection: 'row', gap: spacing.md },
  chevron: { color: colors.primary, fontSize: 28, fontWeight: '300' },
  container: { gap: spacing.lg, padding: spacing.lg },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  grid: { flexDirection: 'row', gap: spacing.sm },
  hero: { backgroundColor: colors.elevated, borderRadius: 22, gap: spacing.sm, padding: spacing.lg },
  heroTop: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  metric: { color: colors.text, fontSize: 36, fontWeight: '900' },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  pressed: { opacity: 0.75 },
  project: { alignItems: 'center', backgroundColor: colors.surface, borderRadius: 16, flexDirection: 'row', gap: spacing.md, justifyContent: 'space-between', padding: spacing.md },
  projectCopy: { flex: 1, gap: spacing.xs },
  projectName: { color: colors.text, fontSize: 16, fontWeight: '800' },
  section: { gap: spacing.sm },
  subtitle: { color: colors.muted, fontSize: 15, lineHeight: 21 },
  task: { backgroundColor: colors.surface, borderRadius: 16, gap: spacing.xs, padding: spacing.md },
  taskTitle: { color: colors.text, flex: 1, fontSize: 15, fontWeight: '800' },
  taskTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' },
  title: { color: colors.text, fontSize: 30, fontWeight: '900', letterSpacing: -0.5 },
  warning: { color: colors.warning, fontSize: 13, fontWeight: '800' },
  warningText: { color: colors.warning },
});
