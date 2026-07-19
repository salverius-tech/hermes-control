import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { EmptyState } from '@/components/EmptyState';
import { SectionHeader } from '@/components/SectionHeader';
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
    <View style={styles.intro}><Text style={styles.muted}>Review the reason first, then choose the smallest safe action.</Text></View>
    {offline || stale ? <Text style={styles.warning}>Offline or stale data. Reconnect to reconcile with Hermes.</Text> : null}
    {!apiToken ? <Text style={styles.muted}>Configure the Control API in Settings.</Text> : null}
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <SectionHeader count={attention.length} title="Open items" />
    {!loading && !attention.length ? <EmptyState body="Approvals, blockers, and failures will appear here." title="All clear" /> : null}
    {attention.filter(isAttentionTask).map((task) => <Link key={task.task_id} href={`/tasks/${task.task_id}`} asChild><Pressable onPress={() => void markSeen(task.task_id)} style={({ pressed }) => [styles.card, pressed && styles.pressed]}><View style={styles.top}><View style={styles.titleCopy}><Text numberOfLines={2} style={styles.taskTitle}>{task.title}</Text><Text numberOfLines={1} style={styles.project}>{task.project_id}</Text></View><StatusPill status={task.status} /></View><Text numberOfLines={3} style={styles.message}>{task.blocker_message || task.error || 'Review this task.'}</Text><View style={styles.footer}><Text style={styles.category}>{task.blocker_category || (task.status === 'awaiting_approval' ? 'Approval required' : task.status)}</Text><Text style={styles.meta}>{task.blocker_retryable ? 'Retryable' : 'Review required'}</Text></View></Pressable></Link>)}
  </ScrollView>;
}

const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, borderRadius: 18, gap: spacing.sm, padding: spacing.md }, category: { color: colors.warning, fontSize: 11, fontWeight: '900', textTransform: 'uppercase' }, container: { gap: spacing.md, padding: spacing.lg }, error: { color: colors.danger }, footer: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' }, intro: { gap: spacing.xs }, message: { color: colors.text, fontSize: 14, lineHeight: 20 }, meta: { color: colors.muted, fontSize: 12 }, muted: { color: colors.muted, fontSize: 14, lineHeight: 20 }, pressed: { opacity: 0.75 }, project: { color: colors.muted, fontSize: 12, marginTop: 2 }, taskTitle: { color: colors.text, fontSize: 16, fontWeight: '800' }, titleCopy: { flex: 1 }, top: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' }, warning: { color: colors.warning, fontSize: 13, fontWeight: '800' } });
