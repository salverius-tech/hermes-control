import { Link } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { WorkThreadSummary } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { MetadataRow } from '@/components/MetadataRow';
import { SectionHeader } from '@/components/SectionHeader';
import { StatusPill } from '@/components/StatusPill';
import { inboxWorkThreadState } from '@/features/tasks/inbox-work-thread-state';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useDataStore } from '@/state/data-store';
import { colors, spacing } from '@/theme/tokens';

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const { workThreads, projects, websocket, offline, lastSync } = useDataStore();

  const { attentionRequired, active, recentlyResolved } = inboxWorkThreadState(workThreads);
  const connectionStatus = offline || websocket === 'disconnected' ? 'offline' : websocket === 'connected' ? 'busy' : 'idle';

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]} showsVerticalScrollIndicator={false}>
      <View style={styles.hero}>
        <View style={styles.heroTop}><Text style={styles.eyebrow}>HERMES CONTROL</Text><StatusPill status={connectionStatus} /></View>
        <Text style={styles.title}>Work inbox</Text>
        <Text style={styles.subtitle}>Review what needs a decision, then return to the right project.</Text>
      </View>
      {offline ? <Text style={styles.warning}>Showing the last available state. Reconnect to reconcile.</Text> : null}
      {!lastSync && !offline ? <ActivityIndicator color={colors.primary} /> : null}


      <View style={styles.section}><SectionHeader actionHref="/attention" actionLabel="View all" count={attentionRequired.length} title="Needs attention" />
        {attentionRequired.slice(0, 3).map((thread) => <WorkThreadRow key={thread.root_task_id} thread={thread} />)}
        {(!lastSync && !offline) ? null : attentionRequired.length === 0 ? <EmptyState body="Approvals, blockers, and failures will appear here." title="All clear" /> : null}
      </View>

      <View style={styles.section}><SectionHeader actionHref="/tasks" actionLabel="View all" count={active.length} title="Active work" />
        {active.slice(0, 3).map((thread) => <WorkThreadRow key={thread.root_task_id} thread={thread} />)}
        {(!lastSync && !offline) ? null : active.length === 0 ? <EmptyState body="Start a task from a project when you are ready." title="Nothing running" /> : null}
      </View>

      <View style={styles.section}><SectionHeader actionHref="/tasks" actionLabel="View all" count={recentlyResolved.length} title="Recent work" />
        {recentlyResolved.slice(0, 3).map((thread) => <WorkThreadRow key={thread.root_task_id} thread={thread} />)}
        {(!lastSync && !offline) ? null : recentlyResolved.length === 0 ? <EmptyState body="Resolved work will appear here after it finishes." title="No recent work" /> : null}
      </View>

      <View style={styles.section}><SectionHeader actionHref="/projects" actionLabel="View all" count={projects.length} title="Projects" />
        {projects.slice(0, 4).map((project) => <Link key={project.project_id} href={`/projects/${encodeURIComponent(project.project_id)}`} asChild><Pressable style={({ pressed }) => [styles.project, pressed && styles.pressed]}><View style={styles.projectCopy}><Text numberOfLines={1} style={styles.projectName}>{project.name}</Text><MetadataRow label="Active" value={`${project.running_count + project.queued_count} tasks`} /></View><Text style={styles.chevron}>›</Text></Pressable></Link>)}
        {(!lastSync && !offline) ? null : projects.length === 0 ? <EmptyState body="Configure the API in Settings to load workspaces." title="No projects yet" /> : null}
      </View>
    </ScrollView>
  );
}

function WorkThreadRow({ thread }: { thread: WorkThreadSummary }) {
  const latest = thread.latest_attempt;
  const attemptCount = thread.attempts.length;
  return <Link href={`/tasks/${latest.task_id}`} asChild><Pressable style={({ pressed }) => [styles.task, pressed && styles.pressed]}><View style={styles.taskTop}><Text numberOfLines={2} style={styles.taskTitle}>{latest.title}</Text><StatusPill status={latest.status} /></View><Text numberOfLines={1} style={styles.muted}>{thread.project_id} · {attemptCount} immutable attempt{attemptCount === 1 ? '' : 's'}</Text></Pressable></Link>;
}

const styles = StyleSheet.create({
  chevron: { color: colors.primary, fontSize: 28, fontWeight: '300' },
  container: { gap: spacing.lg, padding: spacing.lg },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  hero: { backgroundColor: colors.elevated, borderRadius: 22, gap: spacing.sm, padding: spacing.lg },
  heroTop: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
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
});
