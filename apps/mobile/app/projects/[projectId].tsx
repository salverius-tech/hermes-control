import { Link, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, ProjectSummary, SessionSummary, TaskSummary } from '@/api/client';
import { StatusPill } from '@/components/StatusPill';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

function taskNeedsAttention(task: TaskSummary) {
  return task.status === 'awaiting_approval' || task.status === 'failed' || task.status === 'blocked';
}

export default function ProjectDetailScreen() {
  const { projectId } = useLocalSearchParams<{ projectId: string }>();
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const decodedProjectId = decodeURIComponent(projectId || '');
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        setLoading(true);
        const [projectResult, sessionResult, taskResult] = await Promise.all([
          apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(decodedProjectId)}`),
          apiFetch<SessionSummary[]>(apiUrl, apiToken, `/sessions?project_id=${encodeURIComponent(decodedProjectId)}`),
          apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks'),
        ]);
        if (!mounted) return;
        setProject(projectResult);
        setSessions(sessionResult);
        setTasks(taskResult.filter((task) => task.project_id === decodedProjectId));
        setError(null);
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : 'Failed to load project');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    if (apiToken && decodedProjectId) void load();
    return () => { mounted = false; };
  }, [apiToken, apiUrl, decodedProjectId]);

  const attention = tasks.filter(taskNeedsAttention);
  const active = tasks.filter((task) => task.status === 'running' || task.status === 'queued');
  const grouped = useMemo(() => {
    const groups = new Map<string, TaskSummary[]>();
    for (const task of tasks) {
      const key = task.root_task_id || task.session_id || task.parent_task_id || task.task_id;
      groups.set(key, [...(groups.get(key) || []), task]);
    }
    return [...groups.values()].sort((a, b) => Date.parse(b[0].updated_at) - Date.parse(a[0].updated_at));
  }, [tasks]);

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {project ? (
        <>
          <View style={styles.header}>
            <View><Text style={styles.title}>{project.name}</Text><Text style={styles.id}>{project.project_id}</Text></View>
            <Link href={{ pathname: '/projects/manage', params: { projectId: project.project_id } }} asChild><Pressable><Text style={styles.link}>Manage</Text></Pressable></Link>
            {project.description ? <Text style={styles.muted}>{project.description}</Text> : null}
            {project.primary_folder ? <Text style={styles.folder}>Primary folder: {project.primary_folder}</Text> : null}
          </View>
          <Link href={{ pathname: '/new-task', params: { projectId: project.project_id } }} asChild>
            <Pressable style={styles.primaryButton}><Text style={styles.primaryButtonText}>Start task in this project</Text></Pressable>
          </Link>
          <Section title="Needs attention" count={attention.length} attention>
            {attention.map((task) => <TaskRow key={task.task_id} task={task} />)}
            {!attention.length ? <Text style={styles.muted}>Nothing needs your input.</Text> : null}
          </Section>
          <Section title="Active work" count={active.length}>
            {active.map((task) => <TaskRow key={task.task_id} task={task} />)}
            {!active.length ? <Text style={styles.muted}>No active tasks.</Text> : null}
          </Section>
          <Section title="Work threads" count={grouped.length}>
            {grouped.map((group) => <ThreadCard key={group[0].root_task_id || group[0].session_id || group[0].task_id} tasks={group} />)}
            {!grouped.length ? <Text style={styles.muted}>No task history in this project.</Text> : null}
          </Section>
          <Section title="Hermes sessions" count={sessions.length}>
            {sessions.slice(0, 10).map((session) => (
              <View key={session.session_id} style={styles.session}><Text style={styles.sessionTitle}>{session.title || 'Untitled session'}</Text><Text style={styles.muted}>{session.session_id}</Text></View>
            ))}
          </Section>
        </>
      ) : null}
    </ScrollView>
  );
}

function Section({ title, count, attention, children }: { title: string; count: number; attention?: boolean; children: React.ReactNode }) {
  return <View style={styles.section}><View style={styles.sectionHeader}><Text style={styles.sectionTitle}>{title}</Text><Text style={[styles.count, attention && styles.attention]}>{count}</Text></View>{children}</View>;
}

function TaskRow({ task }: { task: TaskSummary }) {
  return <Link href={`/tasks/${task.task_id}`} asChild><Pressable style={({ pressed }) => [styles.task, pressed && styles.pressed]}><View style={styles.taskTop}><Text style={styles.taskTitle} numberOfLines={2}>{task.title}</Text><StatusPill status={task.status} /></View><Text style={styles.taskMeta}>{task.relation || 'original'} · {new Date(task.updated_at).toLocaleString()}</Text></Pressable></Link>;
}

function ThreadCard({ tasks }: { tasks: TaskSummary[] }) {
  const [expanded, setExpanded] = useState(tasks.some(taskNeedsAttention));
  const latest = tasks[0];
  return <View style={styles.thread}><Pressable accessibilityRole="button" onPress={() => setExpanded((value) => !value)}><View style={styles.taskTop}><Text style={styles.taskTitle} numberOfLines={2}>{latest.title}</Text><StatusPill status={latest.status} /></View><Text style={styles.taskMeta}>{tasks.length} immutable attempt{tasks.length === 1 ? '' : 's'} · {expanded ? 'Collapse' : 'Expand'}</Text><Text style={styles.taskMeta}>{latest.result_summary || latest.error || latest.blocker_message || 'No final result yet'}</Text></Pressable>{expanded ? tasks.slice().sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)).map((task) => <TaskRow key={task.task_id} task={task} />) : null}</View>;
}

const styles = StyleSheet.create({
  attention: { color: colors.warning },
  container: { gap: spacing.lg, padding: spacing.lg },
  count: { color: colors.muted, fontWeight: '900' },
  error: { color: colors.danger, fontSize: 15 },
  folder: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  header: { backgroundColor: colors.elevated, borderColor: colors.border, borderRadius: 24, borderWidth: 1, gap: spacing.xs, padding: spacing.lg },
  id: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  link: { color: colors.primary, fontWeight: '800' },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  pressed: { opacity: 0.75 },
  primaryButton: { backgroundColor: colors.primary, borderRadius: 18, padding: spacing.md },
  primaryButtonText: { color: colors.text, fontSize: 16, fontWeight: '900', textAlign: 'center' },
  section: { gap: spacing.sm },
  sectionHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  sectionTitle: { color: colors.text, fontSize: 20, fontWeight: '900' },
  session: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 3, padding: spacing.md },
  sessionTitle: { color: colors.text, fontWeight: '800' },
  task: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: spacing.xs, padding: spacing.md },
  taskMeta: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  taskTitle: { color: colors.text, flex: 1, fontSize: 16, fontWeight: '800' },
  taskTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' },
  thread: { backgroundColor: colors.elevated, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: spacing.sm, padding: spacing.md },
  title: { color: colors.text, fontSize: 30, fontWeight: '900' },
});
