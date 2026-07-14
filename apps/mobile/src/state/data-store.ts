import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import { apiFetch, AgentStatus, Diagnostics, ProjectSummary, SessionSummary, TaskSummary } from '@/api/client';
import { createEventsSocket, parseLiveEvent } from '@/api/events';
import { useSettingsStore } from './settings';

const CACHE_KEY = 'hmc.data.v1';
const ATTENTION_KEY = 'hmc.attention.seen.v1';
export const isAttentionTask = (task: TaskSummary) => ['awaiting_approval', 'blocked', 'failed'].includes(task.status);

function attentionItems(tasks: TaskSummary[]) { return tasks.filter(isAttentionTask); }
function mergeTask(tasks: TaskSummary[], next: TaskSummary) { return [next, ...tasks.filter((task) => task.task_id !== next.task_id)]; }
async function readSeen(): Promise<Record<string, string>> { try { return JSON.parse((await AsyncStorage.getItem(ATTENTION_KEY)) || '{}') as Record<string, string>; } catch { return {}; } }
async function unreadCount(tasks: TaskSummary[]): Promise<number> { const seen = await readSeen(); return attentionItems(tasks).filter((task) => seen[task.task_id] !== task.updated_at).length; }

type DataState = {
  tasks: TaskSummary[]; projects: ProjectSummary[]; sessions: SessionSummary[]; agents: AgentStatus[]; attention: TaskSummary[]; diagnostics: Diagnostics | null;
  websocket: 'disconnected' | 'connecting' | 'connected'; lastSync: string | null; stale: boolean; offline: boolean; unreadAttention: number;
  refresh: () => Promise<void>; connect: () => () => void; markAttentionSeen: (taskId: string) => Promise<void>;
};

export const useDataStore = create<DataState>((set, get) => ({
  tasks: [], projects: [], sessions: [], agents: [], attention: [], diagnostics: null, websocket: 'disconnected', lastSync: null, stale: false, offline: false, unreadAttention: 0,
  async refresh() {
    const { apiUrl, apiToken } = useSettingsStore.getState(); if (!apiToken) return;
    try {
      const [tasks, projects, sessions, agents, diagnostics] = await Promise.all([
        apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks'), apiFetch<ProjectSummary[]>(apiUrl, apiToken, '/projects'),
        apiFetch<SessionSummary[]>(apiUrl, apiToken, '/sessions'), apiFetch<AgentStatus[]>(apiUrl, apiToken, '/agents'), apiFetch<Diagnostics>(apiUrl, apiToken, '/diagnostics'),
      ]);
      const attention = attentionItems(tasks);
      const data = { tasks, projects, sessions, agents, attention, diagnostics, lastSync: new Date().toISOString(), stale: false, offline: false, unreadAttention: await unreadCount(tasks) };
      await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(data)); set(data);
    } catch {
      try { const cached = await AsyncStorage.getItem(CACHE_KEY); if (cached) set({ ...(JSON.parse(cached) as DataState), stale: true, offline: true }); else set({ stale: true, offline: true }); } catch { set({ stale: true, offline: true }); }
    }
  },
  connect() {
    const { apiUrl, apiToken } = useSettingsStore.getState(); if (!apiToken) return () => undefined;
    set({ websocket: 'connecting' }); const socket = createEventsSocket(apiUrl, apiToken);
    socket.onopen = () => set({ websocket: 'connected' }); socket.onclose = () => set({ websocket: 'disconnected' }); socket.onerror = () => socket.close();
    socket.onmessage = (message) => { const event = parseLiveEvent(typeof message.data === 'string' ? message.data : ''); if (!event) return;
      if (event.type === 'snapshot') {
        const attention = attentionItems(event.tasks);
        set({ tasks: event.tasks, projects: event.projects, agents: event.agents, attention, stale: false, offline: false });
        void unreadCount(event.tasks).then((unreadAttention) => set({ unreadAttention }));
      } else {
        set((state) => { const tasks = mergeTask(state.tasks, event.task); return { tasks, attention: attentionItems(tasks), stale: false, offline: false }; });
        void unreadCount(mergeTask(get().tasks, event.task)).then((unreadAttention) => set({ unreadAttention }));
      }
    }; return () => socket.close();
  },
  async markAttentionSeen(taskId) { const seen = await readSeen(); const item = get().attention.find((task) => task.task_id === taskId); if (item) seen[taskId] = item.updated_at; await AsyncStorage.setItem(ATTENTION_KEY, JSON.stringify(seen)); set({ unreadAttention: get().attention.filter((task) => seen[task.task_id] !== task.updated_at).length }); },
}));
