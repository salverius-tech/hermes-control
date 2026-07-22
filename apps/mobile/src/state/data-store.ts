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
export function mergeTask(tasks: TaskSummary[], next: TaskSummary) {
  const current = tasks.find((task) => task.task_id === next.task_id);
  if (current && Date.parse(current.updated_at) > Date.parse(next.updated_at)) return tasks;
  return [next, ...tasks.filter((task) => task.task_id !== next.task_id)];
}
async function readSeen(): Promise<Record<string, string>> { try { return JSON.parse((await AsyncStorage.getItem(ATTENTION_KEY)) || '{}') as Record<string, string>; } catch { return {}; } }
async function unreadCount(tasks: TaskSummary[]): Promise<number> { const seen = await readSeen(); return attentionItems(tasks).filter((task) => seen[task.task_id] !== task.updated_at).length; }

export function normalizeCachedData(cached: unknown): Partial<DataState> {
  const data = cached && typeof cached === 'object' && !Array.isArray(cached) ? cached as Partial<DataState> : {};
  const tasks = Array.isArray(data.tasks) ? data.tasks : [];
  const workThreads = Array.isArray(data.workThreads)
    ? data.workThreads
    : tasks.map((task) => ({ root_task_id: task.root_task_id || task.task_id, project_id: task.project_id, attempts: [task], latest_attempt: task, latest_outcome: task.status }));
  return { ...data, workThreads };
}

type DataState = {
  tasks: TaskSummary[]; workThreads: WorkThreadSummary[]; projects: ProjectSummary[]; sessions: SessionSummary[]; agents: AgentStatus[]; attention: TaskSummary[]; queuedTasks: QueuedTask[]; diagnostics: Diagnostics | null;
  websocket: 'disconnected' | 'connecting' | 'connected'; websocketUrl: string | null; websocketError: string | null; websocketCloseCode: number | null; websocketCloseReason: string | null; websocketReconnects: number;
  lastSync: string | null; stale: boolean; offline: boolean; unreadAttention: number; lastEventSequence: number | null; sequenceGap: boolean;
  refresh: () => Promise<void>; syncQueuedTasks: () => Promise<QueuedTask[]>; connect: () => () => void; markAttentionSeen: (taskId: string) => Promise<void>;
};

export const useDataStore = create<DataState>((set, get) => ({
  tasks: [], workThreads: [], projects: [], sessions: [], agents: [], attention: [], queuedTasks: [], diagnostics: null, websocket: 'disconnected', websocketUrl: null, websocketError: null, websocketCloseCode: null, websocketCloseReason: null, websocketReconnects: 0, lastSync: null, stale: false, offline: false, unreadAttention: 0, lastEventSequence: null, sequenceGap: false,
  async syncQueuedTasks() {
    const queuedTasks = await loadTaskQueue(AsyncStorage);
    set({ queuedTasks });
    return queuedTasks;
  },
  async refresh() {
    const { apiUrl, apiToken } = useSettingsStore.getState(); if (!apiToken) return;
    try {
      await flushTaskQueue(AsyncStorage, apiUrl, apiToken);
      const queuedTasks = await get().syncQueuedTasks();
      const [tasks, workThreads, projects, sessions, agents, diagnostics] = await Promise.all([
        apiFetch<TaskSummary[]>(apiUrl, apiToken, '/tasks?include_archived=true'), fetchWorkThreads(apiUrl, apiToken, { includeArchived: true }), apiFetch<ProjectSummary[]>(apiUrl, apiToken, '/projects'),
        apiFetch<SessionSummary[]>(apiUrl, apiToken, '/sessions'), apiFetch<AgentStatus[]>(apiUrl, apiToken, '/agents'), apiFetch<Diagnostics>(apiUrl, apiToken, '/diagnostics'),
      ]);
      const attention = attentionItems(tasks);
      const data = { tasks, workThreads, projects, sessions, agents, attention, queuedTasks, diagnostics, lastSync: new Date().toISOString(), stale: false, offline: false, unreadAttention: await unreadCount(tasks) };
      await AsyncStorage.setItem(CACHE_KEY, JSON.stringify(data)); set(data);
    } catch {
      // Flush can update the durable queue even when the subsequent API snapshot
      // cannot be loaded. Read it again so a stale cached snapshot never hides a
      // newly queued offline submission.
      let queuedTasks = get().queuedTasks;
      try { queuedTasks = await get().syncQueuedTasks(); } catch { /* retain the last in-memory queue */ }
      try { const cached = await AsyncStorage.getItem(CACHE_KEY); if (cached) set({ ...normalizeCachedData(JSON.parse(cached)), queuedTasks, stale: true, offline: true }); else set({ queuedTasks, stale: true, offline: true }); } catch { set({ queuedTasks, stale: true, offline: true }); }
    }
  },
  connect() {
    const { apiUrl, apiToken } = useSettingsStore.getState(); if (!apiToken) return () => undefined;
    let stopped = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconciliationTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;
    let connectionEpoch = 0;
    const reconcile = () => {
      if (stopped || reconciliationTimer) return;
      reconciliationTimer = setTimeout(() => { reconciliationTimer = null; void get().refresh(); }, 250);
    };
    const websocketUrl = redactWebSocketUrl(buildWebSocketUrl(apiUrl, apiToken));

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer) return;
      const delay = Math.min(30000, 1000 * 2 ** Math.min(attempts, 5));
      attempts += 1;
      set((state) => ({ websocket: 'connecting', websocketReconnects: state.websocketReconnects + 1 }));
      reconnectTimer = setTimeout(() => { reconnectTimer = null; open(); }, delay);
    };
    const open = () => {
      if (stopped) return;
      const epoch = ++connectionEpoch;
      let receivedSnapshot = false;
      const isCurrent = () => !stopped && epoch === connectionEpoch;
      set({ websocket: 'connecting', websocketUrl, websocketError: null });
      const currentSocket = createEventsSocket(apiUrl, apiToken);
      socket = currentSocket;
      currentSocket.onopen = () => {
        if (!isCurrent()) return;
        attempts = 0;
        set({ websocket: 'connected', websocketError: null, offline: false });
        void get().refresh();
      };
      currentSocket.onclose = (event) => {
        if (!isCurrent()) return;
        set({ websocket: 'disconnected', websocketCloseCode: event.code, websocketCloseReason: event.reason || null });
        scheduleReconnect();
      };
      currentSocket.onerror = () => {
        if (!isCurrent()) return;
        set({ websocketError: 'WebSocket connection error' });
        currentSocket.close();
      };
      currentSocket.onmessage = (message) => {
        if (!isCurrent()) return;
        const event = parseLiveEvent(typeof message.data === 'string' ? message.data : ''); if (!event) return;
        if (event.type === 'snapshot') {
          const lastEventSequence = get().lastEventSequence;
          // A new socket's first snapshot is authoritative, even when the API
          // restarted and its sequence counter is lower than the previous one.
          // Later duplicate snapshots on that same socket remain stale.
          if (receivedSnapshot && lastEventSequence !== null && event.seq <= lastEventSequence) return;
          receivedSnapshot = true;
          const attention = attentionItems(event.tasks);
          set({ tasks: event.tasks, projects: event.projects, agents: event.agents, attention, stale: false, offline: false, lastSync: new Date().toISOString(), lastEventSequence: event.seq, sequenceGap: false });
          void unreadCount(event.tasks).then((unreadAttention) => set({ unreadAttention }));
          reconcile();
        } else {
          if (!receivedSnapshot) return;
          const lastEventSequence = get().lastEventSequence;
          if (lastEventSequence !== null && event.seq <= lastEventSequence) return;
          const expected = lastEventSequence === null ? event.seq : lastEventSequence + 1;
          const gap = event.seq !== expected;
          set((state) => { const tasks = mergeTask(state.tasks, event.task); return { tasks, attention: attentionItems(tasks), stale: gap, offline: false, lastSync: new Date().toISOString(), lastEventSequence: event.seq, sequenceGap: gap }; });
          if (gap) void get().refresh();
          else reconcile();
          void unreadCount(get().tasks).then((unreadAttention) => set({ unreadAttention }));
        }
      };
    };
    set({ websocketReconnects: 0 });
    open();
    return () => {
      stopped = true;
      connectionEpoch += 1;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (reconciliationTimer) clearTimeout(reconciliationTimer);
      reconnectTimer = null;
      reconciliationTimer = null;
      socket?.close();
      set({ websocket: 'disconnected' });
    };
  },
  async markAttentionSeen(taskId) { const seen = await readSeen(); const item = get().attention.find((task) => task.task_id === taskId); if (item) seen[taskId] = item.updated_at; await AsyncStorage.setItem(ATTENTION_KEY, JSON.stringify(seen)); set({ unreadAttention: get().attention.filter((task) => seen[task.task_id] !== task.updated_at).length }); },
}));
