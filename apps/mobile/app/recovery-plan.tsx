import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fetchRecoveryPlan, RecoveryPlanEntry } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { MetadataRow } from '@/components/MetadataRow';
import { SectionHeader } from '@/components/SectionHeader';
import { StatusPill } from '@/components/StatusPill';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

const statusDescription: Record<RecoveryPlanEntry['status'], string> = {
  already_registered: 'Already registered with Hermes.',
  ready: 'Ready for an operator-confirmed recovery.',
  missing_repository: 'The declared repository folder is missing.',
  conflict: 'A project with this slug uses another workspace.',
  blocked: 'The workspace manifest needs attention.',
};

function entryTitle(entry: RecoveryPlanEntry): string {
  return entry.slug || entry.workspace.split('/').filter(Boolean).at(-1) || 'Invalid workspace';
}

export default function RecoveryPlanScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [entries, setEntries] = useState<RecoveryPlanEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadPlan = useCallback(async () => {
    if (!apiToken) { setEntries([]); setError('Configure an API token in Settings to review recovery plans.'); setLoading(false); return; }
    setLoading(true); setError(null);
    try { setEntries((await fetchRecoveryPlan(apiUrl, apiToken)).entries); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to load recovery plan'); }
    finally { setLoading(false); }
  }, [apiToken, apiUrl]);

  useEffect(() => { void loadPlan(); }, [loadPlan]);

  return <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]} refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void loadPlan()} refreshing={loading} />}>
    <Text style={styles.intro}>Read-only recovery readiness for managed workspaces. Restoring a project requires a separate explicit operator action.</Text>
    <SectionHeader count={entries.length} title="Recovery plans" />
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {error ? <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text> : null}
    {!loading && !error && entries.length === 0 ? <EmptyState body="No managed workspace recovery descriptors were found." title="No recovery plans" /> : null}
    {entries.map((entry) => <RecoveryPlanCard entry={entry} key={`${entry.workspace}:${entry.slug || entry.status}`} />)}
  </ScrollView>;
}

function RecoveryPlanCard({ entry }: { entry: RecoveryPlanEntry }) {
  return <View style={styles.card}>
    <View style={styles.cardTop}><View style={styles.copy}><Text numberOfLines={1} style={styles.title}>{entryTitle(entry)}</Text><Text style={styles.description}>{statusDescription[entry.status]}</Text></View><StatusPill status={entry.status} /></View>
    {entry.detail ? <Text style={styles.detail}>{entry.detail}</Text> : null}
    <View style={styles.metadata}><MetadataRow label="Workspace" value={entry.workspace} /></View>
  </View>;
}

const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, borderRadius: 18, gap: spacing.md, padding: spacing.md }, cardTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' }, container: { gap: spacing.lg, padding: spacing.lg }, copy: { flex: 1, gap: spacing.xs }, description: { color: colors.muted, fontSize: 13, lineHeight: 18 }, detail: { color: colors.warning, fontSize: 13, lineHeight: 18 }, error: { color: colors.danger, fontSize: 14, lineHeight: 20 }, intro: { color: colors.muted, fontSize: 14, lineHeight: 20 }, metadata: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.sm }, title: { color: colors.text, fontSize: 17, fontWeight: '800' } });
