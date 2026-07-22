import { Link, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, fetchWorkThreads, ProjectSummary, SessionSummary, TaskSummary, WorkThreadSummary } from '@/api/client';
import { StatusPill } from '@/components/StatusPill';
import { inboxWorkThreadState } from '@/features/tasks/inbox-work-thread-state';
import { workspaceFolderState } from '@/features/projects/workspace-state';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function ProjectDetailScreen() {
  const { projectId } = useLocalSearchParams<{ projectId: string }>();
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const decodedProjectId = decodeURIComponent(projectId || '');
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [workThreads, setWorkThreads] = useState<WorkThreadSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        setLoading(true);
        const [projectResult, sessionResult, workThreadResult] = await Promise.all([
          apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(decodedProjectId)}`),
          apiFetch<SessionSummary[]>(apiUrl, apiToken, `/sessions?project_id=${encodeURIComponent(decodedProjectId)}`),
          fetchWorkThreads(apiUrl, apiToken, { projectId: decodedProjectId }),
        ]);
        if (!mounted) return;
        setProject(projectResult);
        setSessions(sessionResult);
        setWorkThreads(workThreadResult);
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

  const threadState = useMemo(() => inboxWorkThreadState(workThreads), [workThreads]);
  const folders = project ? workspaceFolderState(project) : null;

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      {loading ? <ActivityIndicator color={colors.primary} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {project ? (
        <View testID={`project-detail-${project.project_id}`}>
          <View style={styles.header} testID="project-detail-header">
            <View><Text style={styles.title}>{project.name}</Text><Text style={styles.id}>{project.project_id}</Text></View>
            {project.description ? <Text style={styles.muted}>{project.description}</Text> : null}
          </View>
          <Link href={{ pathname: '/new-task', params: { projectId: project.project_id } }} asChild>
            <Pressable style={styles.primaryButton}><Text style={styles.primaryButtonText}>Start task in this project</Text></Pressable>
          </Link>
          <Section attention testID="project-section-attention" title="Needs attention" count={threadState.attentionRequired.length}>
            {threadState.attentionRequired.map((thread) => <ThreadCard key={thread.root_task_id} thread={thread} />)}
            {!threadState.attentionRequired.length ? <Text style={styles.muted}>No work threads need review.</Text> : null}
          </Section>
          <Section testID="project-section-active" title="Active work" count={threadState.active.length}>
            {threadState.active.map((thread) => <ThreadCard key={thread.root_task_id} thread={thread} />)}
            {!threadState.active.length ? <Text style={styles.muted}>No work is currently running or queued.</Text> : null}
          </Section>
          <Section testID="project-section-recent" title="Recent work threads" count={threadState.recentlyResolved.length}>
            {threadState.recentlyResolved.map((thread) => <ThreadCard key={thread.root_task_id} thread={thread} />)}
            {!threadState.recentlyResolved.length ? <Text style={styles.muted}>No completed work threads in this project.</Text> : null}
          </Section>
          <Section testID="project-section-sessions" title="Hermes sessions" count={sessions.length}>
            {sessions.slice(0, 5).map((session) => (
              <View key={session.session_id} style={styles.session} testID={`project-session-${session.session_id}`}><Text style={styles.sessionTitle}>{session.title || 'Untitled session'}</Text><Text style={styles.muted} numberOfLines={1}>{session.preview || 'No session preview available'}</Text></View>
            ))}
            {!sessions.length ? <Text style={styles.muted}>No Hermes sessions for this project.</Text> : null}
          </Section>
          <Section testID="project-section-workspace" title="Workspace & repository">
            <View style={styles.workspaceState}>
              <Text style={styles.workspaceLabel}>Workspace primary folder</Text>
              <Text selectable style={styles.folder} testID="project-workspace-primary-folder">{folders?.primaryFolder || 'No primary folder registered'}</Text>
              <Text style={styles.workspaceLabel}>Repository folder</Text>
              <Text selectable style={styles.folder} testID="project-workspace-repository-folder">{folders?.repositoryFolder || 'Workspace-only — no repository folder registered'}</Text>
              <Link href={{ pathname: '/projects/manage', params: { projectId: project.project_id } }} asChild><Pressable testID="project-manage"><Text style={styles.link}>Manage workspace & repository</Text></Pressable></Link>
            </View>
          </Section>
        </View>
      ) : null}
    </ScrollView>
  );
}

function Section({ title, count, attention, children, testID }: { title: string; count?: number; attention?: boolean; children: React.ReactNode; testID: string }) {
  return <View style={styles.section} testID={testID}><View style={styles.sectionHeader}><Text style={styles.sectionTitle}>{title}</Text>{count === undefined ? null : <Text style={[styles.count, attention && styles.attention]}>{count}</Text>}</View>{children}</View>;
}

function TaskRow({ task }: { task: TaskSummary }) {
  return <Link href={`/tasks/${task.task_id}`} asChild><Pressable style={({ pressed }) => [styles.task, pressed && styles.pressed]}><View style={styles.taskTop}><Text style={styles.taskTitle} numberOfLines={2}>{task.title}</Text><StatusPill status={task.status} /></View><Text style={styles.taskMeta}>{task.relation || 'original'} · {new Date(task.updated_at).toLocaleString()}</Text></Pressable></Link>;
}

function ThreadCard({ thread }: { thread: WorkThreadSummary }) {
  const tasks = thread.attempts;
  const latest = thread.latest_attempt;
  const needsAttention = ['awaiting_approval', 'attention_required', 'blocked', 'failed'].includes(latest.status);
  const [expanded, setExpanded] = useState(needsAttention);
  useEffect(() => { if (needsAttention) setExpanded(true); }, [needsAttention]);
  return <View style={styles.thread} testID={`project-thread-${thread.root_task_id}`}><Pressable accessibilityRole="button" onPress={() => setExpanded((value) => !value)}><View style={styles.taskTop}><Text style={styles.taskTitle} numberOfLines={2}>{latest.title}</Text><StatusPill status={latest.status} /></View><Text style={styles.taskMeta}>{tasks.length} immutable attempt{tasks.length === 1 ? '' : 's'} · {expanded ? 'Collapse' : 'Expand'}</Text><Text style={styles.taskMeta}>{latest.result_summary || latest.error || latest.blocker_message || 'No final result yet'}</Text></Pressable>{expanded ? tasks.slice().sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at)).map((task) => <TaskRow key={task.task_id} task={task} />) : null}</View>;
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
  workspaceLabel: { color: colors.text, fontSize: 13, fontWeight: '800' },
  workspaceState: { borderTopColor: colors.border, borderTopWidth: 1, gap: 3, marginTop: spacing.sm, paddingTop: spacing.sm },
});
