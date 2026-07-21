import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, createProject, ProjectOrigin, ProjectSummary } from '@/api/client';
import { initialProjectCreateForm, validateProjectCreateForm } from '@/features/projects/project-create-form';
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
  const [origin, setOrigin] = useState<ProjectOrigin>(initialProjectCreateForm.origin);
  const [repositoryUrl, setRepositoryUrl] = useState('');
  const [project, setProject] = useState<ProjectSummary | null>(null);
  const [directories, setDirectories] = useState<string[]>([]);
  const [browserPath, setBrowserPath] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const creationValidation = validateProjectCreateForm({ name, description, folder, origin, repositoryUrl });

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
    if (!editing && !creationValidation.request) {
      setError(Object.values(creationValidation.errors).join(' '));
      return;
    }
    if (editing && !name.trim()) return;
    try {
      setSaving(true); setError(null);
      let result: ProjectSummary;
      if (editing) {
        result = await apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}`, { method: 'PATCH', body: JSON.stringify({ name: name.trim(), description, primary_folder: folder || undefined }) });
      } else {
        result = await createProject(apiUrl, apiToken, creationValidation.request!);
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

  async function setPrimary(path: string) {
    if (!editing) { setFolder(path); return; }
    try { const result = await apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}`, { method: 'PATCH', body: JSON.stringify({ primary_folder: path }) }); setProject(result); setFolder(path); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to set primary folder'); }
  }

  async function removeFolder(path: string) {
    if (!editing) return;
    try { const result = await apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}/folders`, { method: 'DELETE', body: JSON.stringify({ path }) }); setProject(result); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to remove folder'); }
  }

  async function archiveProject() {
    if (!editing) return;
    try { await apiFetch<ProjectSummary>(apiUrl, apiToken, `/projects/${encodeURIComponent(projectId || '')}`, { method: 'PATCH', body: JSON.stringify({ archived: !project?.archived }) }); router.replace('/projects'); }
    catch (err) { setError(err instanceof Error ? err.message : 'Failed to update archive state'); }
  }

  return <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
    {error ? <Text style={styles.error}>{error}</Text> : null}
    <Text style={styles.label}>Name</Text><TextInput onChangeText={setName} style={styles.input} value={name} />
    <Text style={styles.label}>Description</Text><TextInput multiline onChangeText={setDescription} style={[styles.input, styles.multiline]} value={description} />
    {!editing ? <><Text style={styles.label}>Start from</Text><View style={styles.originRow}>{(['workspace', 'clone', 'adopt'] as ProjectOrigin[]).map((item) => <Pressable key={item} onPress={() => setOrigin(item)} style={[styles.origin, origin === item && styles.originSelected]}><Text style={[styles.originText, origin === item && styles.originTextSelected]}>{item === 'workspace' ? 'Workspace' : item === 'clone' ? 'Clone repo' : 'Adopt folder'}</Text></Pressable>)}</View><Text style={styles.help}>{origin === 'workspace' ? 'Create a managed workspace with notes and artifacts.' : origin === 'clone' ? 'Clone a remote repository into a new managed workspace.' : 'Register an existing approved folder as a native project.'}</Text></> : null}
    {!editing && origin === 'clone' ? <><Text style={styles.label}>Repository URL</Text><TextInput autoCapitalize="none" autoCorrect={false} onChangeText={setRepositoryUrl} placeholder="https://example.com/team/repository.git" placeholderTextColor={colors.muted} style={styles.input} value={repositoryUrl} /><Text style={styles.help}>Use a credential-free HTTPS or SSH URL.</Text></> : null}
    {(editing || origin === 'adopt') ? <><Text style={styles.label}>Folder path</Text><TextInput autoCapitalize="none" onChangeText={setFolder} placeholder="/home/anvil/repos/example" placeholderTextColor={colors.muted} style={styles.input} value={folder} />
      <Text style={styles.help}>Manual paths are validated by the Control API against approved project roots.</Text>
      <View style={styles.browserHeader}><Text style={styles.label}>Browse approved folders</Text>{browserPath ? <Pressable onPress={() => void loadDirectories()}><Text style={styles.link}>Root</Text></Pressable> : null}</View>
      {browserPath ? <Text style={styles.help}>{browserPath}</Text> : null}
      {directories.map((directory) => <View key={directory} style={styles.directory}><Pressable onPress={() => void loadDirectories(directory)} style={styles.directoryBrowse}><Text style={styles.directoryText}>{directory}</Text></Pressable><Pressable onPress={() => void addFolder(directory)}><Text style={styles.link}>Use</Text></Pressable></View>)}
      {browserPath ? null : <ActivityIndicator color={colors.primary} />}</> : null}
    {project?.folders.map((item) => <View key={item} style={styles.folderRow}><Text style={styles.help}>{item}</Text><View style={styles.folderActions}>{item !== project.primary_folder ? <Pressable onPress={() => void setPrimary(item)}><Text style={styles.link}>Primary</Text></Pressable> : <Text style={styles.primary}>Primary</Text>}<Pressable onPress={() => void removeFolder(item)}><Text style={styles.remove}>Remove</Text></Pressable></View></View>)}
    <Pressable disabled={saving || (editing ? !name.trim() : !creationValidation.request)} onPress={() => void saveProject()} style={[styles.button, (saving || (editing ? !name.trim() : !creationValidation.request)) && styles.disabled]}><Text style={styles.buttonText}>{saving ? 'Saving…' : editing ? 'Save project' : origin === 'clone' ? 'Clone and create project' : origin === 'adopt' ? 'Adopt project' : 'Create workspace'}</Text></Pressable>
    {editing ? <Pressable onPress={() => void archiveProject()} style={styles.archiveButton}><Text style={styles.remove}>{project?.archived ? 'Restore project' : 'Archive project'}</Text></Pressable> : null}
  </ScrollView>;
}

const styles = StyleSheet.create({
  archiveButton: { borderColor: colors.danger, borderRadius: 18, borderWidth: 1, padding: spacing.md },
  browserHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  button: { backgroundColor: colors.primary, borderRadius: 18, padding: spacing.md },
  buttonText: { color: colors.text, fontWeight: '900', textAlign: 'center' },
  container: { gap: spacing.md, padding: spacing.lg },
  directory: { alignItems: 'center', backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, flexDirection: 'row', justifyContent: 'space-between', padding: spacing.md },
  directoryBrowse: { flex: 1 },
  directoryText: { color: colors.text, flex: 1, fontSize: 13 },
  disabled: { opacity: 0.5 },
  error: { color: colors.danger },
  folderActions: { alignItems: 'flex-end', gap: spacing.xs },
  folderRow: { borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing.sm },
  help: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  input: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, color: colors.text, padding: spacing.md },
  label: { color: colors.text, fontSize: 16, fontWeight: '800' },
  link: { color: colors.primary, fontWeight: '800' },
  multiline: { minHeight: 100, textAlignVertical: 'top' },
  origin: { borderColor: colors.border, borderRadius: 14, borderWidth: 1, flex: 1, padding: spacing.sm },
  originRow: { flexDirection: 'row', gap: spacing.xs },
  originSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  originText: { color: colors.text, fontSize: 12, fontWeight: '800', textAlign: 'center' },
  originTextSelected: { color: colors.background },
  primary: { color: colors.success, fontSize: 12, fontWeight: '800' },
  remove: { color: colors.danger, fontSize: 12, fontWeight: '800' },
});
