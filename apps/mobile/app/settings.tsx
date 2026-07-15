import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, Diagnostics, testConnection } from '@/api/client';
import { ActionButton } from '@/components/ActionButton';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { useDataStore } from '@/state/data-store';
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
    try {
      await save({ apiUrl: draftUrl.trim(), apiToken: draftToken.trim() });
      setSaveMessage('Settings saved');
    } catch (err) {
      setSaveMessage('Settings failed');
      Alert.alert('Settings failed', err instanceof Error ? err.message : 'Unknown error');
    }
  }

  async function checkConnection() {
    try {
      const ok = await testConnection(draftUrl.trim(), draftToken.trim());
      Alert.alert(ok ? 'Connection OK' : 'Connection failed');
    } catch (err) {
      Alert.alert('Connection failed', err instanceof Error ? err.message : 'Unknown error');
    }
  }

  async function loadDiagnostics() {
    try {
      const result = await apiFetch<Diagnostics>(draftUrl.trim(), draftToken.trim(), '/diagnostics');
      setDiagnostics(result);
    } catch (err) {
      Alert.alert('Diagnostics failed', err instanceof Error ? err.message : 'Unknown error');
    }
  }

  return (
    <ScrollView
      contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.label}>Control API URL</Text>
      <TextInput autoCapitalize="none" onChangeText={setDraftUrl} style={styles.input} testID="settings-api-url" value={draftUrl} />
      <Text style={styles.label}>API token</Text>
      <TextInput autoCapitalize="none" onChangeText={setDraftToken} secureTextEntry style={styles.input} testID="settings-api-token" value={draftToken} />
      <ActionButton label="Save settings" onPress={saveSettings} testID="settings-save" variant="primary" />
      {saveMessage ? (
        <Text accessibilityLiveRegion="polite" style={styles.success} testID="settings-save-message">
          {saveMessage}
        </Text>
      ) : null}
      <ActionButton label="Test connection" onPress={checkConnection} testID="settings-test-connection" />
      <ActionButton disabled={!draftToken.trim()} label="Load diagnostics" onPress={loadDiagnostics} testID="settings-load-diagnostics" />
      {diagnostics ? (
        <MetricCard title="Diagnostics" subtitle={`API ${diagnostics.version}`}>
          <Text style={styles.help}>Storage: {diagnostics.storage}</Text>
          <Text style={styles.help}>Schema: {diagnostics.schema_version}</Text>
          <Text style={styles.help}>Execution: {diagnostics.execution_mode}</Text>
          <Text style={styles.help}>Notifications: {diagnostics.notification_mode}</Text>
          <Text style={styles.help}>Events: {diagnostics.websocket_path}</Text>
        </MetricCard>
      ) : null}
      <MetricCard title="Connection state">
        <Text style={styles.help}>Authentication: {draftToken.trim() ? 'configured' : 'not configured'}</Text>
        <Text style={styles.help}>WebSocket: {websocket}</Text>
        <Text style={styles.help}>WebSocket endpoint: {websocketUrl || 'not configured'}</Text>
        {websocketError ? <Text style={styles.help}>WebSocket error: {websocketError}</Text> : null}
        {websocketCloseCode !== null ? <Text style={styles.help}>WebSocket close: {websocketCloseCode}{websocketCloseReason ? ` (${websocketCloseReason})` : ''}</Text> : null}
        <Text style={styles.help}>Last successful sync: {lastSync ? new Date(lastSync).toLocaleString() : 'not yet'}</Text>
        <Text style={styles.help}>Data: {offline || stale ? 'offline/stale' : 'current'}</Text>
      </MetricCard>
      <Text style={styles.help}>Use your PC LAN IP or Tailscale host when testing from a physical Android device.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  help: {
    color: colors.muted,
    lineHeight: 20,
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.text,
    padding: spacing.md,
  },
  label: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
  },
  success: {
    color: colors.success,
    fontSize: 14,
    fontWeight: '800',
  },
});
