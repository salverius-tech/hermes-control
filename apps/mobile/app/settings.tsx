import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, Diagnostics, testConnection } from '@/api/client';
import { ExpandableDetails } from '@/components/ExpandableDetails';
import { ActionButton } from '@/components/ActionButton';
import { MetadataRow } from '@/components/MetadataRow';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useDataStore } from '@/state/data-store';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function SettingsScreen() {
  const { apiUrl, apiToken, save } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [draftUrl, setDraftUrl] = useState(apiUrl);
  const [draftToken, setDraftToken] = useState(apiToken);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const { websocket, websocketUrl, websocketError, websocketCloseCode, websocketCloseReason, lastSync, offline, stale } = useDataStore();

  async function saveSettings() {
    setSaveMessage('Saving settings...');
    try { await save({ apiUrl: draftUrl.trim(), apiToken: draftToken.trim() }); setSaveMessage('Settings saved'); }
    catch (err) { setSaveMessage('Settings failed'); Alert.alert('Settings failed', err instanceof Error ? err.message : 'Unknown error'); }
  }

  async function checkConnection() {
    try { await testConnection(draftUrl.trim(), draftToken.trim()); Alert.alert('Connection OK'); }
    catch (err) { Alert.alert('Connection failed', err instanceof Error ? err.message : 'Unknown error'); }
  }

  async function loadDiagnostics() {
    try { setDiagnostics(await apiFetch<Diagnostics>(draftUrl.trim(), draftToken.trim(), '/diagnostics')); }
    catch (err) { Alert.alert('Diagnostics failed', err instanceof Error ? err.message : 'Unknown error'); }
  }

  return <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + spacing.xl }]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
    <Text style={styles.title}>Settings</Text>
    <Text style={styles.intro}>Keep the connection details here; technical state stays below the actions.</Text>

    <MetricCard title="Connection">
      <Text style={styles.label}>Control API URL</Text>
      <TextInput autoCapitalize="none" onChangeText={setDraftUrl} style={styles.input} testID="settings-api-url" value={draftUrl} />
      <Text style={styles.label}>API token</Text>
      <TextInput autoCapitalize="none" secureTextEntry onChangeText={setDraftToken} style={styles.input} testID="settings-api-token" value={draftToken} />
      <ActionButton label="Save settings" onPress={saveSettings} testID="settings-save" variant="primary" />
      {saveMessage ? <Text accessibilityLiveRegion="polite" style={styles.success} testID="settings-save-message">{saveMessage}</Text> : null}
      <ActionButton label="Test authenticated connection" onPress={checkConnection} testID="settings-test-connection" />
    </MetricCard>

    <MetricCard title="Connection state">
      <MetadataRow label="Authentication" value={draftToken.trim() ? 'Configured' : 'Not configured'} />
      <MetadataRow label="WebSocket" value={websocket} />
      <MetadataRow label="Last sync" value={lastSync ? new Date(lastSync).toLocaleString() : 'Not yet'} />
      <MetadataRow label="Data" value={offline || stale ? 'Offline / stale' : 'Current'} />
      <MetadataRow label="Endpoint" value={websocketUrl || 'Not configured'} />
      {websocketError ? <Text style={styles.error}>{websocketError}</Text> : null}
      {websocketCloseCode !== null ? <Text style={styles.error}>Closed · {websocketCloseCode}{websocketCloseReason ? ` · ${websocketCloseReason}` : ''}</Text> : null}
    </MetricCard>

    <ExpandableDetails label="Diagnostics">
      <ActionButton disabled={!draftToken.trim()} label="Load diagnostics" onPress={loadDiagnostics} testID="settings-load-diagnostics" />
      {diagnostics ? <><MetadataRow label="API" value={diagnostics.version} /><MetadataRow label="Storage" value={diagnostics.storage} /><MetadataRow label="Schema" value={diagnostics.schema_version} /><MetadataRow label="Execution" value={diagnostics.execution_mode} /><MetadataRow label="Events" value={diagnostics.websocket_path} /></> : <Text style={styles.help}>Load authenticated diagnostics when you need backend details.</Text>}
    </ExpandableDetails>
    <Text style={styles.help}>Use a PC LAN IP or Tailscale host when testing from a physical Android device.</Text>
  </ScrollView>;
}

const styles = StyleSheet.create({ container: { gap: spacing.md, padding: spacing.lg }, error: { color: colors.danger, fontSize: 13, lineHeight: 19 }, help: { color: colors.muted, fontSize: 13, lineHeight: 19 }, input: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.text, minHeight: 48, paddingHorizontal: spacing.md }, intro: { color: colors.muted, fontSize: 14, lineHeight: 20 }, label: { color: colors.muted, fontSize: 12, fontWeight: '800', marginBottom: -spacing.xs, textTransform: 'uppercase' }, success: { color: colors.success, fontSize: 13, fontWeight: '800' }, title: { color: colors.text, fontSize: 30, fontWeight: '900' } });
