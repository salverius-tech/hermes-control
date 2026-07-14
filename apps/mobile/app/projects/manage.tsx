import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, ProjectSummary } from '@/api/client';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { colors, spacing } from '@/theme/tokens';

export default function ProjectManageScreen() {
  const { projectId } = useLocalSearchParams<{ projectId?: string }>();
  const router = useRouter();
  const { apiUrl, apiToken } = useSettingsStore();
  const insets = useSafeAreaInsets();
  const editing = Boolean(projectId);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [folder, setFolder] = useState('');
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [directories, setDirectories] = useState<string[]>([]);
  const [browserPath, setBrowserPath] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!apiToken) return;
    if (editing) {
      void apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}`).then((result) => {
        setProject(result); setName(result.name); setDescription(result.description || ''); setFolder(result.primary_folder || '');
      }).catch((err) => setError(err instanceof Error ? err.message : 'Failed to load project'));
    }
    void loadDirectories();
  }, [apiToken, apiUrl, projectId]);

  async function loadDirectories(path?: string) {
    try { setDirectories(await apiFetch<string[]>(apiUrl, apiToken, `/folders${path ? `?path=${encodeURIComponent(path)}` : ''}`)); setBrowserPath(path); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to load folders'); }
  }

  async function saveProject() {
    if (!name.trim()) return;
    try {
      setSaving(true); setError(null);
      let result: ProjectSummary;
      if (editing) {
        result = await apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}`, { method: 'PATCH', body: JSON.stringify({ name: name.trim(), description, primary_folder: folder || undefined }) });
      } else {
        result = await apiFetch<ProjectSummary>(apiUrl, apiToken, '/projects', { method: 'POST', body: JSON.stringify({ name: name.trim(), description, folders: folder ? [folder] : [] }) });
      }
      router.replace(`/projects/${encodeURIComponent(result.project_id)}`);
    } catch (err) { setError(err instanceof Error ? err.message : 'Failed to save project'); }
    finally { setSaving(false); }
  }

  async function addFolder(path: string) {
    if (!editing || !path) { setFolder(path); return; }
    try { const result = await apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}/folders`, { method: 'POST', body: JSON.stringify({ path }) }); setProject(result); setFolder(result.primary_folder || ''); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to add folder'); }
  }

  return <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
    <Text style={styles.title}>{editing ? 'Manage project' : 'New Hermes project'}</Text>
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <Text style={styles.label}>Name</Text><TextInput onChangeText={setName} style={styles.input} value={name} />
    <Text style={styles.label}>Description</Text><TextInput multiline onChangeText={setDescription} style={[styles.input, styles.multiline]} value={description} />
    <Text style={styles.label}>Folder path</Text><TextInput autoCapitalize="none" onChangeText={setFolder} placeholder="/home/anvil/repos/example" placeholderTextColor={colors.muted} style={styles.input} value={folder} />
    <Text style={styles.help}>Manual paths are validated by the Control API against approved project roots.</Text>
    <View style={styles.browserHeader}><Text style={styles.label}>Browse approved folders</Text>{browserPath ? <Pressable onPress={() => void loadDirectories()}><Text style={styles.link}>Root</Text></Pressable> : null}</View>
    {browserPath ? <Text style={styles.help}>{browserPath}</Text> : null}
    {directories.map((directory) => <Pressable key={directory} onPress={() => void loadDirectories(directory)} style={styles.directory}><Text style={styles.directoryText}>{directory}</Text><Pressable onPress={() => void addFolder(directory)}><Text style={styles.link}>Use</Text></Pressable></Pressable>)}
    {browserPath ? null : <ActivityIndicator color={colors.primary} />}
    {project?.folders.map((item) => <View key={item} style={styles.folderRow}><Text style={styles.help}>{item}</Text><Text style={styles.primary}>{item === project.primary_folder ? 'Primary' : ''}</Text></View>)}
    <Pressable disabled={saving || !name.trim()} onPress={() => void saveProject()} style={[styles.button, (saving || !name.trim()) && styles.disabled]}><Text style={styles.buttonText}>{saving ? 'Saving…' : editing ? 'Save project' : 'Create project'}</Text></Pressable>
  </ScrollView>;
}

const styles = StyleSheet.create({
  browserHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  button: { backgroundColor: colors.primary, borderRadius: 18, padding: spacing.md },
  buttonText: { color: colors.text, fontWeight: '900', textAlign: 'center' },
  container: { gap: spacing.md, padding: spacing.lg },
  directory: { alignItems: 'center', backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, flexDirection: 'row', justifyContent: 'space-between', padding: spacing.md },
  directoryText: { color: colors.text, flex: 1, fontSize: 13 },
  disabled: { opacity: 0.5 },
  error: { color: colors.danger },
  folderRow: { borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing.sm },
  help: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  input: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, color: colors.text, padding: spacing.md },
  label: { color: colors.text, fontSize: 16, fontWeight: '800' },
  link: { color: colors.primary, fontWeight: '800' },
  multiline: { minHeight: 100, textAlignVertical: 'top' },
  primary: { color: colors.success, fontSize: 12, fontWeight: '800' },
  title: { color: colors.text, fontSize: 28, fontWeight: '900' },
});
