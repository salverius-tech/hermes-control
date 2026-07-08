import { useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, TextInput } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { testConnection } from '@/api/client';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function SettingsScreen() {
  const { apiUrl, apiToken, save } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const [draftUrl, setDraftUrl] = useState(apiUrl);
  const [draftToken, setDraftToken] = useState(apiToken);

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
      <Text style={styles.help}>Use your PC LAN IP or Tailscale host when testing from a physical Android device.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
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
