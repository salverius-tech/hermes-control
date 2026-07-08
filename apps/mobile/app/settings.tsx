import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, Diagnostics, testConnection } from '@/api/client';
import { MetricCard } from '@/components/MetricCard';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function SettingsScreen() {
  const { apiUrl, apiToken, save } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [draftUrl, setDraftUrl] = useState(apiUrl);
  const [draftToken, setDraftToken] = useState(apiToken);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);

  async function saveSettings() {
    await save({ apiUrl: draftUrl.trim(), apiToken: draftToken.trim() });
    Alert.alert('Settings saved');
  }

  async function checkConnection() {
    try {
      const ok = await testConnection(draftUrl.trim());
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
    <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
      <Text style={styles.label}>Control API URL</Text>
      <TextInput autoCapitalize="none" onChangeText={setDraftUrl} style={styles.input} value={draftUrl} />
      <Text style={styles.label}>API token</Text>
      <TextInput autoCapitalize="none" onChangeText={setDraftToken} secureTextEntry style={styles.input} value={draftToken} />
      <Pressable onPress={saveSettings} style={styles.primaryButton}>
        <Text style={styles.buttonText}>Save settings</Text>
      </Pressable>
      <Pressable onPress={checkConnection} style={styles.secondaryButton}>
        <Text style={styles.buttonText}>Test connection</Text>
      </Pressable>
      <Pressable disabled={!draftToken.trim()} onPress={loadDiagnostics} style={[styles.secondaryButton, !draftToken.trim() && styles.buttonDisabled]}>
        <Text style={styles.buttonText}>Load diagnostics</Text>
      </Pressable>
      {diagnostics ? (
        <MetricCard title="Diagnostics" subtitle={`API ${diagnostics.version}`}>
          <Text style={styles.help}>Storage: {diagnostics.storage}</Text>
          <Text style={styles.help}>Schema: {diagnostics.schema_version}</Text>
          <Text style={styles.help}>Execution: {diagnostics.execution_mode}</Text>
          <Text style={styles.help}>Events: {diagnostics.websocket_path}</Text>
        </MetricCard>
      ) : null}
      <Text style={styles.help}>Use your PC LAN IP or Tailscale host when testing from a physical Android device.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonText: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
    textAlign: 'center',
  },
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
  primaryButton: {
    backgroundColor: colors.primary,
    borderRadius: 18,
    padding: spacing.lg,
  },
  secondaryButton: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    padding: spacing.lg,
  },
});
