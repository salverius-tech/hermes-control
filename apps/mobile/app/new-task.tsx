import AsyncStorage from '@react-native-async-storage/async-storage';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiFetch, TaskSummary } from '@/api/client';
import { clearTaskDraft, loadTaskDraft, saveTaskDraft } from '@/features/tasks/draft';
import { appendTranscript } from '@/features/tasks/prompt';
import { buildTaskCreateRequest, priorityOptions, type TaskPriority } from '@/features/tasks/request';
import { enqueueTask, flushTaskQueue } from '@/features/tasks/offline-queue';
import { applyPromptTemplate, promptTemplates } from '@/features/tasks/templates';
import { ExpandableDetails } from '@/components/ExpandableDetails';
import { bottomNavigationHeight } from '@/navigation/constants';
import { useSettingsStore } from '@/state/settings';
import { useDataStore } from '@/state/data-store';
import { colors, spacing } from '@/theme/tokens';

export default function NewTaskScreen() {
  const { apiUrl, apiToken } = useSettingsStore();
  const projects = useDataStore((state) => state.projects);
  const refreshData = useDataStore((state) => state.refresh);
  const router = useRouter();
  const { projectId: projectParam } = useLocalSearchParams<{ projectId?: string }>();
  const insets = useSafeAreaInsets();
  const [prompt, setPrompt] = useState('');
  const [projectId, setProjectId] = useState('default');
  const [priority, setPriority] = useState<TaskPriority>('normal');
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [partialTranscript, setPartialTranscript] = useState('');
  const [listening, setListening] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [queueNotice, setQueueNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [draftLoaded, setDraftLoaded] = useState(false);
  const skipNextDraftSave = useRef(false);

  useEffect(() => {
    if (!apiToken) return;
    void refreshData();
    void flushTaskQueue(AsyncStorage, apiUrl, apiToken).then((submitted) => {
      if (submitted.length > 0) setQueueNotice(`${submitted.length} queued task${submitted.length === 1 ? '' : 's'} submitted.`);
    });
  }, [apiToken, apiUrl, refreshData]);
  useEffect(() => { if (projectId === 'default') void AsyncStorage.getItem('hmc.lastProject').then((value) => { if (value) setProjectId(value); }); }, [projectId]);

  useEffect(() => {
    if (typeof projectParam === 'string' && projectParam.trim()) setProjectId(projectParam);
  }, [projectParam]);

  useEffect(() => {
    let mounted = true;
    loadTaskDraft(AsyncStorage)
      .then((draft) => {
        if (!mounted || draft === null) return;
        setPrompt(draft.prompt);
        setProjectId(draft.projectId);
        setPriority(draft.priority);
        setRequiresApproval(draft.requiresApproval);
      })
      .finally(() => {
        if (mounted) setDraftLoaded(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!draftLoaded) return;
    if (skipNextDraftSave.current) {
      skipNextDraftSave.current = false;
      return;
    }
    void saveTaskDraft(AsyncStorage, { prompt, projectId, priority, requiresApproval });
  }, [draftLoaded, priority, projectId, prompt, requiresApproval]);

  useSpeechRecognitionEvent('start', () => {
    setVoiceError(null);
    setPartialTranscript('');
    setListening(true);
  });

  useSpeechRecognitionEvent('end', () => {
    setListening(false);
    setPartialTranscript('');
  });

  useSpeechRecognitionEvent('result', (event) => {
    const transcript = event.results[0]?.transcript?.trim();
    if (!transcript) return;

    if (event.isFinal) {
      setPrompt((current) => appendTranscript(current, transcript));
      setPartialTranscript('');
      return;
    }

    setPartialTranscript(transcript);
  });

  useSpeechRecognitionEvent('error', (event) => {
    setListening(false);
    setPartialTranscript('');
    setVoiceError(event.message || `Voice input failed: ${event.error}`);
  });

  async function toggleVoiceInput() {
    try {
      if (listening) {
        ExpoSpeechRecognitionModule.stop();
        return;
      }

      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permission.granted) {
        setVoiceError('Microphone and speech recognition permission are required for voice prompts.');
        return;
      }

      setVoiceError(null);
      ExpoSpeechRecognitionModule.start({
        continuous: false,
        interimResults: true,
        lang: 'en-US',
      });
    } catch (err) {
      setListening(false);
      setPartialTranscript('');
      setVoiceError(err instanceof Error ? `Voice input unavailable: ${err.message}` : 'Voice input is unavailable on this device.');
    }
  }

  async function submit() {
    if (!prompt.trim()) return;
    try {
      setSubmitting(true);
      const request = buildTaskCreateRequest({ prompt, projectId, priority, requiresApproval });
      const idempotencyKey = `mobile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const task = await apiFetch<TaskSummary>(apiUrl, apiToken, '/tasks', {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify(request),
      });
      await AsyncStorage.setItem('hmc.lastProject', request.project_id);
      await clearTaskDraft(AsyncStorage);
      skipNextDraftSave.current = true;
      setPrompt('');
      setProjectId(request.project_id);
      setRequiresApproval(false);
      router.replace(`/tasks/${task.task_id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      if (!message.startsWith('API ')) {
        await enqueueTask(AsyncStorage, request, new Date(), idempotencyKey);
        setQueueNotice('API unavailable. Task saved locally and will retry when the connection returns.');
        return;
      }
      Alert.alert('Task failed', message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ScrollView
      contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.header}>
        <Text style={styles.label}>Instruction</Text>
        <Pressable
          onPress={toggleVoiceInput}
          style={({ pressed }) => [styles.voiceButton, listening && styles.voiceButtonActive, pressed && styles.buttonPressed]}
        >
          <Text style={styles.voiceButtonText}>{listening ? 'Stop voice' : 'Speak prompt'}</Text>
        </Pressable>
      </View>

      <TextInput
        accessibilityLabel="Task instruction"
        accessibilityHint="Describe the work Hermes should perform"
        multiline
        onChangeText={setPrompt}
        placeholder="Tell Hermes what to do..."
        placeholderTextColor={colors.muted}
        style={styles.input}
        testID="new-task-prompt"
        value={prompt}
      />

      <Pressable
        disabled={!prompt.trim() || submitting || !apiToken || !projects.some((project) => project.project_id === projectId && !project.archived)}
        onPress={submit}
        style={({ pressed }) => [
          styles.button,
          (!prompt.trim() || submitting || !apiToken || !projects.some((project) => project.project_id === projectId && !project.archived)) && styles.buttonDisabled,
          pressed && styles.buttonPressed,
        ]}
      >
        <Text style={styles.buttonText}>{submitting ? 'Submitting…' : 'Start Hermes task'}</Text>
      </Pressable>

      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Templates</Text>
        <View style={styles.templateRow}>
          {promptTemplates.map((template) => (
            <Pressable
              key={template.id}
              onPress={() => setPrompt((current) => applyPromptTemplate(current, template.prompt))}
              style={({ pressed }) => [styles.templateChip, pressed && styles.buttonPressed]}
              testID={`new-task-template-${template.id}`}
            >
              <Text style={styles.templateText}>{template.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <ExpandableDetails initiallyExpanded label="Task options">
      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Project</Text>
        <Text style={styles.selectedProject}>{projects.find((project) => project.project_id === projectId)?.name || projectId}</Text>
        <Text style={styles.help}>{projects.find((project) => project.project_id === projectId)?.primary_folder || 'Select an active Hermes project.'}</Text>
        <View style={styles.projectRow}>{projects.filter((project) => !project.archived).map((project) => <Pressable accessibilityRole="button" accessibilityState={{ selected: project.project_id === projectId }} key={project.project_id} onPress={() => setProjectId(project.project_id)} style={[styles.projectChip, project.project_id === projectId && styles.projectChipSelected]}><Text style={styles.segmentText}>{project.name}</Text></Pressable>)}</View>
        {projects.length > 0 && projects.every((project) => project.archived) ? <Text style={styles.error}>All projects are archived. Restore one before creating work.</Text> : null}
      </View>

      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Priority</Text>
        <View style={styles.segmentedRow}>
          {priorityOptions.map((option) => {
            const selected = priority === option.value;
            return (
              <Pressable
                accessibilityRole="button"
                accessibilityState={{ selected }}
                key={option.value}
                onPress={() => setPriority(option.value)}
                style={({ pressed }) => [styles.segment, selected && styles.segmentSelected, pressed && styles.buttonPressed]}
                testID={`new-task-priority-${option.value}`}
              >
                <Text style={[styles.segmentText, selected && styles.segmentTextSelected]}>{option.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>

      <View style={styles.approvalRow}>
        <View style={styles.approvalCopy}>
          <Text style={styles.approvalTitle}>Require approval before running</Text>
          <Text style={styles.help}>Queue this task for review instead of executing immediately.</Text>
        </View>
        <Switch
          onValueChange={setRequiresApproval}
          testID="new-task-requires-approval"
          thumbColor={requiresApproval ? colors.primary : colors.muted}
          value={requiresApproval}
        />
      </View>
      </ExpandableDetails>

      {listening ? <Text style={styles.listening}>Listening… speak your Hermes instruction now.</Text> : null}
      {partialTranscript ? <Text style={styles.partial}>Heard: {partialTranscript}</Text> : null}
      {voiceError ? <Text style={styles.error}>{voiceError}</Text> : null}
      {queueNotice ? <Text style={styles.help}>{queueNotice}</Text> : null}

      {!apiToken ? <Text style={styles.help}>Configure your API token in Settings first.</Text> : null}
      <Text style={styles.help}>Use voice dictation or type directly. Voice transcription stays on-device/OS-level through the phone speech service.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  approvalCopy: {
    flex: 1,
    gap: spacing.xs,
  },
  approvalRow: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    flexDirection: 'row',
    gap: spacing.md,
    padding: spacing.md,
  },
  approvalTitle: {
    color: colors.text,
    fontSize: 16,
    fontWeight: '800',
  },
  button: {
    backgroundColor: colors.primary,
    borderRadius: 18,
    padding: spacing.lg,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  buttonPressed: {
    opacity: 0.8,
  },
  buttonText: {
    color: colors.text,
    fontSize: 17,
    fontWeight: '900',
    textAlign: 'center',
  },
  container: {
    gap: spacing.md,
    padding: spacing.lg,
  },
  error: {
    color: colors.danger,
    fontSize: 14,
    lineHeight: 20,
  },
  fieldGroup: {
    gap: spacing.sm,
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: spacing.md,
    justifyContent: 'space-between',
  },
  help: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
  },
  input: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 20,
    borderWidth: 1,
    color: colors.text,
    fontSize: 16,
    lineHeight: 22,
    minHeight: 180,
    padding: spacing.lg,
    textAlignVertical: 'top',
  },
  label: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '800',
  },
  listening: {
    color: colors.warning,
    fontSize: 14,
    fontWeight: '700',
  },
  partial: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 14,
    borderWidth: 1,
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    padding: spacing.md,
  },
  segment: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  segmentedRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  segmentSelected: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  segmentText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: '800',
  },
  segmentTextSelected: {
    color: colors.text,
  },
  singleLineInput: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.text,
    fontSize: 16,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  projectChip: { borderColor: colors.border, borderRadius: 999, borderWidth: 1, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  projectChipSelected: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  projectRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  selectedProject: { color: colors.text, fontSize: 17, fontWeight: '800' },
  templateChip: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  templateRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  templateText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  voiceButton: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  voiceButtonActive: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  voiceButtonText: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '800',
  },
});
