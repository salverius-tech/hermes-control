import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { StatusPill } from '@/components/StatusPill';
import { bottomNavigationHeight } from '@/navigation/constants';
import { isAttentionTask, useDataStore } from '@/state/data-store';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function AttentionScreen() {
  const { apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const attention = useDataStore((state) => state.attention);
  const offline = useDataStore((state) => state.offline);
  const stale = useDataStore((state) => state.stale);
  const refresh = useDataStore((state) => state.refresh);
  const markSeen = useDataStore((state) => state.markAttentionSeen);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(useCallback(() => { if (!apiToken) return; setLoading(true); void refresh().catch((err) => setError(err instanceof Error ? err.message : 'Failed to load attention')).finally(() => setLoading(false)); }, [apiToken, refresh]));
  const load = async () => { setLoading(true); setError(null); try { await refresh(); } catch (err) { setError(err instanceof Error ? err.message : 'Failed to load attention'); } finally { setLoading(false); } };

  return <ScrollView refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void load()} refreshing={loading} />} contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
    <Text style={styles.title}>Needs attention</Text>
    <Text style={styles.muted}>Approvals, blockers, and failures stay here until you review them.</Text>
    {offline || stale ? <Text style={styles.warning}>Offline or stale data. Reconnect to reconcile with Hermes.</Text> : null}
    {!apiToken ? <Text style={styles.muted}>Configure the Control API in Settings.</Text> : null}
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {error ? <Text style={styles.error}>{error}</Text> : null}
    {!loading && !attention.length ? <Text style={styles.muted}>Nothing needs your attention.</Text> : null}
    {attention.filter(isAttentionTask).map((task) => <Link key={task.task_id} href={`/tasks/${task.task_id}`} asChild><Pressable onPress={() => void markSeen(task.task_id)} style={({ pressed }) => [styles.card, pressed && styles.pressed]}><View style={styles.top}><Text style={styles.taskTitle}>{task.title}</Text><StatusPill status={task.status} /></View><Text style={styles.project}>{task.project_id}{task.session_id ? ` · session ${task.session_id}` : ''}</Text><Text style={styles.category}>{task.blocker_category || (task.status === 'awaiting_approval' ? 'Approval required' : task.status)}</Text><Text style={styles.message}>{task.blocker_message || task.error || 'Review this task.'}</Text><Text style={styles.meta}>{task.blocker_retryable ? 'Retryable' : 'Review required'} · Updated {new Date(task.updated_at).toLocaleString()}</Text></Pressable></Link>)}
  </ScrollView>;
}

const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: spacing.sm, padding: spacing.lg }, category: { color: colors.warning, fontSize: 13, fontWeight: '900', textTransform: 'uppercase' }, container: { gap: spacing.md, padding: spacing.lg }, error: { color: colors.danger }, message: { color: colors.text, fontSize: 15, lineHeight: 21 }, meta: { color: colors.muted, fontSize: 12 }, muted: { color: colors.muted, fontSize: 15, lineHeight: 21 }, pressed: { opacity: 0.75 }, project: { color: colors.muted, fontSize: 13 }, taskTitle: { color: colors.text, flex: 1, fontSize: 17, fontWeight: '800' }, title: { color: colors.text, fontSize: 30, fontWeight: '900' }, top: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' }, warning: { color: colors.warning, fontWeight: '800' } });
