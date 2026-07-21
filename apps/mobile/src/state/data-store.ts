import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import { apiFetch, AgentStatus, Diagnostics, fetchWorkThreads, ProjectSummary, SessionSummary, TaskSummary, WorkThreadSummary } from '@/api/client';
import { createEventsSocket, parseLiveEvent, redactWebSocketUrl } from '@/api/events';
import { buildWebSocketUrl } from '@/api/url';
import { flushTaskQueue, loadTaskQueue, type QueuedTask } from '@/features/tasks/offline-queue';
import { useSettingsStore } from './settings';

const CACHE_KEY = 'hmc.data.v1';
const ATTENTION_KEY = 'hmc.attention.seen.v1';
export const isAttentionTask = (task: TaskSummary) => ['awaiting_approval', 'blocked', 'failed'].includes(task.status);

function attentionItems(tasks: TaskSummary[]) { return tasks.filter(isAttentionTask); }
function mergeTask(tasks: TaskSummary[], next: TaskSummary) {
  const current = tasks.find((task) => task.task_id === next.task_id);
  if (current && Date.parse(current.updated_at) > Date.parse(next.updated_at)) return tasks;
  return [next, ...tasks.filter((task) => task.task_id !== next.task_id)];
}
async function readSeen(): Promise<Record<string, string>> { try { return JSON.parse((await AsyncStorage.getItem(ATTENTION_KEY)) || '{}') as Record<string, string>; } catch { return {}; } }
async function unreadCount(tasks: TaskSummary[]): Promise<number> { const seen = await readSeen(); return attentionItems(tasks).filter((task) => seen[task.task_id] !== task.updated_at).length; }

type DataState = {
  tasks: TaskSummary[]; workThreads: WorkThreadSummary[]; projects: ProjectSummary[]; sessions: SessionSummary[]; agents: AgentStatus[]; attention: TaskSummary[]; queuedTasks: QueuedTask[]; diagnostics: Diagnostics | null;
  websocket: 'disconnected' | 'connecting' | 'connected'; websocketUrl: string | null; websocketError: string | null; websocketCloseCode: number | null; websocketCloseReason: string | null;
  lastSync: string | null; stale: boolean; offline: boolean; unreadAttention: number; lastEventSequence: number | null; sequenceGap: boolean;
  refresh: () => Promise<void>; connect: () => () => void; markAttentionSeen: (taskId: string) => Promise<void>;
};

export const useDataStore = create<DataState>((set, get) => ({
  tasks: [], workThreads: [], projects: [], sessions: [], agents: [], attention: [], queuedTasks: [], diagnostics: null, websocket: 'disconnected', websocketUrl: null, websocketError: null, websocketCloseCode: null, websocketCloseReason: null, lastSync: null, stale: false, offline: false, unreadAttention: 0, lastEventSequence: null, sequenceGap: false,
  async refresh() {
    const { apiUrl, apiToken } = useSettingsStore.getState(); if (!apiToken) return;
    try {
      await flushTaskQueue(AsyncStorage, apiUrl, apiToken);
      const queuedTasks = await loadTaskQueue(AsyncStorage);
      const [tasks, workThreads, projects, sessions, agents, diagnostics] = await Promise.all([
        apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks?include_archived=true'), fetchWorkThreads(apiUrl, apiToken, { includeArchived: true }), apiFetch<ProjectSummary[]>(apiUrl, apiToken, '/projects'),
        apiFetch<SessionSummary[]>(apiUrl, apiToken, '/sessions'), apiFetch<AgentStatus[]>(apiUrl, apiToken, '/agents'), apiFetch<Diagnostics>(apiUrl, apiToken, '/diagnostics'),
      ]);
      const attention = attentionItems(tasks);
      const data = { tasks, workThreads, projects, sessions, agents, attention, queuedTasks, diagnostics, lastSync: new Date().toISOString(), stale: false, offline: false, unreadAttention: await unreadCount(tasks) };
      await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(data)); set(data);
    } catch {
      try { const cached = await AsyncStorage.getItem(CACHE_KEY); if (cached) set({ ...(JSON.parse(cached) as DataState), stale: true, offline: true }); else set({ stale: true, offline: true }); } catch { set({ stale: true, offline: true }); }
    }
  },
  connect() {
    const { apiUrl, apiToken } = useSettingsStore.getState(); if (!apiToken) return () => undefined;
    let stopped = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;
    const websocketUrl = redactWebSocketUrl(buildWebSocketUrl(apiUrl, apiToken));

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer) return;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attempts, 5));
      attempts += 1;
      set({ websocket: 'connecting' });
      reconnectTimer = setTimeout(() => { reconnectTimer = null; open(); }, delay);
    };
    const open = () => {
      if (stopped) return;
      set({ websocket: 'connecting', websocketUrl, websocketError: null });
      socket = createEventsSocket(apiUrl, apiToken);
      socket.onopen = () => { attempts = 0; set({ websocket: 'connected', websocketError: null, offline: false }); void get().refresh(); };
      socket.onclose = (event) => { set({ websocket: 'disconnected', websocketCloseCode: event.code, websocketCloseReason: event.reason || null }); scheduleReconnect(); };
      socket.onerror = () => { set({ websocketError: 'WebSocket connection error' }); socket?.close(); };
      socket.onmessage = (message) => {
        const event = parseLiveEvent(typeof message.data === 'string' ? message.data : ''); if (!event) return;
        if (event.type === 'snapshot') {
          const attention = attentionItems(event.tasks);
          set({ tasks: event.tasks, projects: event.projects, agents: event.agents, attention, stale: false, offline: false, lastSync: new Date().toISOString(), lastEventSequence: event.seq, sequenceGap: false });
          void unreadCount(event.tasks).then((unreadAttention) => set({ unreadAttention }));
        } else {
          const lastEventSequence = get().lastEventSequence;
          const expected = lastEventSequence === null ? event.seq : lastEventSequence + 1;
          const gap = event.seq !== expected;
          set((state) => { const tasks = mergeTask(state.tasks, event.task); return { tasks, attention: attentionItems(tasks), stale: gap, offline: false, lastSync: new Date().toISOString(), lastEventSequence: event.seq, sequenceGap: gap }; });
          if (gap) void get().refresh();
          void unreadCount(get().tasks).then((unreadAttention) => set({ unreadAttention }));
        }
      };
    };
    open();
    return () => { stopped = true; if (reconnectTimer) clearTimeout(reconnectTimer); reconnectTimer = null; socket?.close(); };
  },
  async markAttentionSeen(taskId) { const seen = await readSeen(); const item = get().attention.find((task) => task.task_id === taskId); if (item) seen[taskId] = item.updated_at; await AsyncStorage.setItem(ATTENTION_KEY, JSON.stringify(seen)); set({ unreadAttention: get().attention.filter((task) => seen[task.task_id] !== task.updated_at).length }); },
}));
