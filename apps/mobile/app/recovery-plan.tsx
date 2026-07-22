import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { applyRecoveryPlan, fetchRecoveryPlan, RecoveryPlanEntry } from '@/api/client';
import { EmptyState } from '@/components/EmptyState';
import { MetadataRow } from '@/components/MetadataRow';
import { SectionHeader } from '@/components/SectionHeader';
import { StatusPill } from '@/components/StatusPill';
import { recoverableSlugs, recoveryApplyMessage } from '@/features/projects/recovery-plan-state';
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
  const [restoreMessage, setRestoreMessage] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);

  const loadPlan = useCallback(async () => {
    if (!apiToken) { setEntries([]); setError('Configure an API token in Settings to review recovery plans.'); setLoading(false); return; }
    setLoading(true); setError(null);
    try { setEntries((await fetchRecoveryPlan(apiUrl, apiToken)).entries); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to load recovery plan'); }
    finally { setLoading(false); }
  }, [apiToken, apiUrl]);

  useEffect(() => { void loadPlan(); }, [loadPlan]);

  const readySlugs = recoverableSlugs(entries);
  function confirmRestore() {
    if (!readySlugs.length) return;
    Alert.alert('Restore selected projects?', `This will re-register ${readySlugs.length} reviewed workspace${readySlugs.length === 1 ? '' : 's'} with Hermes.`, [
      { style: 'cancel', text: 'Cancel' },
      { style: 'destructive', text: 'Restore', onPress: () => void restoreReady() },
    ]);
  }

  async function restoreReady() {
    if (!readySlugs.length) return;
    setRestoring(true); setError(null); setRestoreMessage(null);
    try {
      const response = await applyRecoveryPlan(apiUrl, apiToken, readySlugs);
      setRestoreMessage(recoveryApplyMessage(response.results) || 'No projects were restored. Review the refreshed plan.');
      await loadPlan();
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to apply recovery plan'); }
    finally { setRestoring(false); }
  }

  return <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]} refreshControl={<RefreshControl colors={[colors.primary]} onRefresh={() => void loadPlan()} refreshing={loading} />}>
    <Text style={styles.intro}>Read-only recovery readiness for managed workspaces. Restoring a project requires a separate explicit operator action.</Text>
    <SectionHeader count={entries.length} title="Recovery plans" />
    {loading ? <ActivityIndicator color={colors.primary} /> : null}
    {error ? <Text accessibilityLiveRegion="polite" style={styles.error}>{error}</Text> : null}
    {restoreMessage ? <Text accessibilityLiveRegion="polite" style={styles.success} testID="recovery-apply-message">{restoreMessage}</Text> : null}
    {!loading && !error && entries.length === 0 ? <EmptyState body="No managed workspace recovery descriptors were found." title="No recovery plans" /> : null}
    {entries.map((entry) => <RecoveryPlanCard entry={entry} key={`${entry.workspace}:${entry.slug || entry.status}`} />)}
    {readySlugs.length ? <Pressable accessibilityRole="button" disabled={restoring} onPress={confirmRestore} style={[styles.restoreButton, restoring && styles.disabled]} testID="recovery-restore-ready"><Text style={styles.restoreButtonText}>{restoring ? 'Restoring…' : `Restore ${readySlugs.length} ready project${readySlugs.length === 1 ? '' : 's'}`}</Text></Pressable> : null}
  </ScrollView>;
}

function RecoveryPlanCard({ entry }: { entry: RecoveryPlanEntry }) {
  return <View style={styles.card} testID={`recovery-entry-${entry.slug || entry.status}`}>
    <View style={styles.cardTop}><View style={styles.copy}><Text numberOfLines={1} style={styles.title}>{entryTitle(entry)}</Text><Text style={styles.description}>{statusDescription[entry.status]}</Text></View><StatusPill status={entry.status} /></View>
    {entry.detail ? <Text style={styles.detail}>{entry.detail}</Text> : null}
    <View style={styles.metadata}><MetadataRow label="Workspace" value={entry.workspace} /></View>
  </View>;
}

const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, borderRadius: 18, gap: spacing.md, padding: spacing.md }, cardTop: { alignItems: 'flex-start', flexDirection: 'row', gap: spacing.sm, justifyContent: 'space-between' }, container: { gap: spacing.lg, padding: spacing.lg }, copy: { flex: 1, gap: spacing.xs }, description: { color: colors.muted, fontSize: 13, lineHeight: 18 }, detail: { color: colors.warning, fontSize: 13, lineHeight: 18 }, disabled: { opacity: 0.5 }, error: { color: colors.danger, fontSize: 14, lineHeight: 20 }, intro: { color: colors.muted, fontSize: 14, lineHeight: 20 }, metadata: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.sm }, restoreButton: { backgroundColor: colors.primary, borderRadius: 16, padding: spacing.md }, restoreButtonText: { color: colors.background, fontWeight: '900', textAlign: 'center' }, success: { color: colors.success, fontSize: 14, fontWeight: '800' }, title: { color: colors.text, fontSize: 17, fontWeight: '800' } });
