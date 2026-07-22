import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentStatus, ProjectSummary, TaskSummary } from '@/api/client';

type SocketHandlers = {
  onopen: (() => void) | null;
  onclose: ((event: { code: number; reason: string }) => void) | null;
  onerror: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
};

class FakeSocket implements SocketHandlers {
  onopen: SocketHandlers['onopen'] = null;
  onclose: SocketHandlers['onclose'] = null;
  onerror: SocketHandlers['onerror'] = null;
  onmessage: SocketHandlers['onmessage'] = null;
  close = vi.fn(() => this.onclose?.({ code: 1000, reason: '' }));

  open() { this.onopen?.(); }
  receive(event: unknown) { this.onmessage?.({ data: JSON.stringify(event) }); }
  closeWith(code = 1006, reason = 'network lost') { this.onclose?.({ code, reason }); }
}

const mocks = vi.hoisted(() => ({
  sockets: [] as FakeSocket[],
  refresh: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  createEventsSocket: vi.fn(),
  apiFetch: vi.fn().mockResolvedValue([]),
  fetchWorkThreads: vi.fn().mockResolvedValue([]),
  flushTaskQueue: vi.fn().mockResolvedValue([]),
  loadTaskQueue: vi.fn().mockResolvedValue([]),
  getItem: vi.fn().mockResolvedValue(null),
  setItem: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@react-native-async-storage/async-storage', () => ({
  default: { getItem: mocks.getItem, setItem: mocks.setItem },
}));
vi.mock('expo-secure-store', () => ({ getItemAsync: vi.fn(), setItemAsync: vi.fn() }));
vi.mock('@/api/client', () => ({ apiFetch: mocks.apiFetch, fetchWorkThreads: mocks.fetchWorkThreads }));
vi.mock('@/api/events', () => ({
  createEventsSocket: mocks.createEventsSocket,
  parseLiveEvent: (data: string) => JSON.parse(data),
  redactWebSocketUrl: (url: string) => url.replace(/token=[^&]*/, 'token=[REDACTED]'),
}));
vi.mock('@/api/url', () => ({ buildWebSocketUrl: () => 'ws://control.test/events?token=secret' }));
vi.mock('@/features/tasks/offline-queue', () => ({
  flushTaskQueue: mocks.flushTaskQueue,
  loadTaskQueue: mocks.loadTaskQueue,
}));
vi.mock('./settings', () => ({
  useSettingsStore: { getState: () => ({ apiUrl: 'http://control.test', apiToken: 'secret' }) },
}));

import { mergeTask, normalizeCachedData, useDataStore } from './data-store';

const task = (taskId: string, status: TaskSummary['status'] = 'running'): TaskSummary => ({
  task_id: taskId, title: taskId, prompt: taskId, status, project_id: 'project-1', source: 'mobile', priority: 'normal', requires_approval: false,
  created_at: '2026-07-21T10:00:00Z', updated_at: '2026-07-21T10:00:00Z', progress_log: [],
});
const project: ProjectSummary = { project_id: 'project-1', name: 'Project', folders: [], archived: false, queued_count: 0, running_count: 0, completed_count: 0, failed_count: 0 };
const agent: AgentStatus = { agent_id: 'agent-1', status: 'idle', project_id: 'project-1' };
const snapshot = (seq: number, tasks: TaskSummary[]) => ({ type: 'snapshot' as const, seq, tasks, projects: [project], agents: [agent] });
const taskUpdate = (seq: number, next: TaskSummary) => ({ type: 'task.updated' as const, seq, task: next });

function resetStore() {
  useDataStore.setState({
    tasks: [], workThreads: [], projects: [], sessions: [], agents: [], attention: [], queuedTasks: [], diagnostics: null,
    websocket: 'disconnected', websocketUrl: null, websocketError: null, websocketCloseCode: null, websocketCloseReason: null, websocketReconnects: 0,
    lastSync: null, stale: false, offline: false, unreadAttention: 0, lastEventSequence: null, sequenceGap: false, refresh: mocks.refresh,
  });
}

function connectSocket(): { socket: FakeSocket; disconnect: () => void } {
  const disconnect = useDataStore.getState().connect();
  const socket = mocks.sockets.at(-1);
  if (!socket) throw new Error('expected a WebSocket connection');
  socket.open();
  mocks.refresh.mockClear();
  return { socket, disconnect };
}

describe('normalizeCachedData', () => {
  it('derives one work thread per task for legacy cached data', () => {
    const legacyTask = { project_id: 'ops', root_task_id: null, status: 'completed', task_id: 'task-1' };

    expect(normalizeCachedData({ tasks: [legacyTask], stale: false })).toMatchObject({
      tasks: [legacyTask], stale: false,
      workThreads: [{ root_task_id: 'task-1', project_id: 'ops', attempts: [legacyTask], latest_attempt: legacyTask, latest_outcome: 'completed' }],
    });
  });

  it('preserves cached work threads from current cache data', () => {
    const workThreads = [{ root_task_id: 'task-1' }];
    expect(normalizeCachedData({ workThreads })).toMatchObject({ workThreads });
  });
});

describe('offline queue reconciliation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStore();
  });

  it('keeps a newly persisted queue entry visible when a cached project snapshot is followed by an unreachable API', async () => {
    const queued = {
      local_id: 'local-mobile-request-1', idempotency_key: 'mobile-request-1', request: { prompt: 'offline device queue task', project_id: 'project-1', priority: 'normal' as const, requires_approval: false },
      state: 'retrying' as const, attempts: 1, created_at: '2026-07-21T12:00:00Z', next_attempt_at: '2026-07-21T12:00:02Z',
    };
    mocks.flushTaskQueue.mockResolvedValue([]);
    mocks.loadTaskQueue.mockResolvedValue([queued]);
    mocks.apiFetch.mockRejectedValue(new Error('network unavailable'));
    mocks.getItem.mockResolvedValue(JSON.stringify({ projects: [project], queuedTasks: [] }));
    useDataStore.setState({ refresh: useDataStore.getInitialState().refresh });

    await useDataStore.getState().refresh();

    expect(useDataStore.getState()).toMatchObject({ offline: true, projects: [project], queuedTasks: [queued] });
    expect(mocks.loadTaskQueue).toHaveBeenCalledTimes(2);
  });
});

describe('live task reconciliation', () => {
  let disconnect: (() => void) | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-21T12:00:00Z'));
    mocks.sockets.length = 0;
    vi.clearAllMocks();
    mocks.refresh.mockResolvedValue(undefined);
    mocks.createEventsSocket.mockImplementation(() => {
      const socket = new FakeSocket();
      mocks.sockets.push(socket);
      return socket;
    });
    resetStore();
  });

  afterEach(() => {
    disconnect?.();
    disconnect = undefined;
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('replaces state from a snapshot and reconciles it after the debounce interval', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;

    connection.socket.receive(snapshot(10, [task('task-1', 'blocked')]));

    expect(useDataStore.getState()).toMatchObject({
      tasks: [task('task-1', 'blocked')], projects: [project], agents: [agent], lastEventSequence: 10, sequenceGap: false, stale: false,
    });
    vi.advanceTimersByTime(249);
    expect(mocks.refresh).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it('applies the next ordered task event after a snapshot', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.receive(snapshot(10, [task('task-1')]));

    const completed = { ...task('task-1', 'completed'), updated_at: '2026-07-21T12:01:00Z' };
    connection.socket.receive(taskUpdate(11, completed));

    expect(useDataStore.getState()).toMatchObject({ tasks: [completed], lastEventSequence: 11, sequenceGap: false, stale: false });
  });

  it('ignores stale snapshots after a newer sequence has been accepted', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.receive(snapshot(10, [task('task-1', 'running')]));
    connection.socket.receive(snapshot(9, [task('stale-task', 'failed')]));

    expect(useDataStore.getState()).toMatchObject({ tasks: [task('task-1', 'running')], lastEventSequence: 10 });
  });

  it('ignores duplicate and stale task events', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    const running = task('task-1', 'running');
    const completed = { ...task('task-1', 'completed'), updated_at: '2026-07-21T12:01:00Z' };
    connection.socket.receive(snapshot(10, [running]));
    connection.socket.receive(taskUpdate(11, completed));
    connection.socket.receive(taskUpdate(11, running));
    connection.socket.receive(taskUpdate(9, { ...running, status: 'failed' }));

    expect(useDataStore.getState()).toMatchObject({ tasks: [completed], lastEventSequence: 11, sequenceGap: false });
  });

  it('marks a sequence gap stale and refreshes immediately', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.receive(snapshot(10, [task('task-1')]));
    mocks.refresh.mockClear();

    const completed = { ...task('task-1', 'completed'), updated_at: '2026-07-21T12:01:00Z' };
    connection.socket.receive(taskUpdate(12, completed));

    expect(useDataStore.getState()).toMatchObject({ tasks: [completed], lastEventSequence: 12, sequenceGap: true, stale: true });
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it('reconnects after a close and clears pending reconnect and reconciliation timers on cleanup', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.receive(snapshot(10, [task('task-1')]));
    connection.socket.closeWith();

    expect(useDataStore.getState()).toMatchObject({ websocket: 'connecting', websocketCloseCode: 1006, websocketCloseReason: 'network lost', websocketReconnects: 1 });
    vi.advanceTimersByTime(1000);
    expect(mocks.sockets).toHaveLength(2);

    const replacement = mocks.sockets[1];
    replacement.open();
    mocks.refresh.mockClear();
    replacement.receive(snapshot(11, [task('task-2')]));
    disconnect();
    disconnect = undefined;
    vi.advanceTimersByTime(30000);

    expect(replacement.close).toHaveBeenCalledTimes(1);
    expect(mocks.refresh).not.toHaveBeenCalled();
    expect(mocks.sockets).toHaveLength(2);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears the previous close diagnostic when a replacement socket connects', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.closeWith();

    vi.advanceTimersByTime(1000);
    const replacement = mocks.sockets[1];
    replacement.open();

    expect(useDataStore.getState()).toMatchObject({
      websocket: 'connected',
      websocketCloseCode: null,
      websocketCloseReason: null,
    });
  });

  it('accepts the replacement socket snapshot after an API sequence reset', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.receive(snapshot(10, [task('before-restart', 'running')]));
    connection.socket.closeWith(1012, 'service restart');
    vi.advanceTimersByTime(1000);

    const replacement = mocks.sockets[1];
    replacement.open();
    replacement.receive(snapshot(0, [task('after-restart', 'completed')]));

    expect(useDataStore.getState()).toMatchObject({
      websocket: 'connected', websocketReconnects: 1, tasks: [task('after-restart', 'completed')], lastEventSequence: 0, sequenceGap: false, stale: false,
    });
  });

  it('ignores late callbacks from a replaced socket while accepting its successor', () => {
    const connection = connectSocket();
    disconnect = connection.disconnect;
    connection.socket.receive(snapshot(10, [task('current', 'running')]));
    connection.socket.closeWith();
    vi.advanceTimersByTime(1000);

    const replacement = mocks.sockets[1];
    replacement.open();
    replacement.receive(snapshot(11, [task('replacement', 'completed')]));
    connection.socket.receive(snapshot(99, [task('stale-socket', 'failed')]));
    connection.socket.closeWith(1006, 'late close');

    expect(useDataStore.getState()).toMatchObject({
      websocket: 'connected', websocketReconnects: 1, tasks: [task('replacement', 'completed')], lastEventSequence: 11,
    });
    expect(mocks.sockets).toHaveLength(2);
  });

  it('ignores out-of-order task updates and accepts newer state', () => {
    const current = { task_id: 'task-1', updated_at: '2026-07-21T10:00:00Z', status: 'running' };
    const stale = { ...current, updated_at: '2026-07-21T09:00:00Z', status: 'queued' };
    const newer = { ...current, updated_at: '2026-07-21T11:00:00Z', status: 'completed' };

    expect(mergeTask([current] as never, stale as never)).toEqual([current]);
    expect(mergeTask([current] as never, newer as never)).toEqual([newer]);
  });
});
