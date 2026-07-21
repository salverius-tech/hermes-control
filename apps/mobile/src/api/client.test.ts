import { describe, expect, it, vi } from 'vitest';

import { fetchRecoveryPlan, fetchWorkThreads, testConnection } from './client';

const workThread = {
  attempts: [],
  latest_attempt: {
    created_at: '2026-07-21T12:00:00Z',
    priority: 'normal',
    progress_log: [],
    project_id: 'ops',
    prompt: 'Repair deployment',
    requires_approval: false,
    source: 'mobile',
    status: 'completed',
    task_id: 'task-retry',
    title: 'Repair deployment',
    updated_at: '2026-07-21T12:01:00Z',
  },
  latest_outcome: 'completed',
  project_id: 'ops',
  root_task_id: 'task-root',
};

describe('fetchWorkThreads', () => {
  it('fetches the work-thread projection with encoded filters', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe('http://localhost:8787/work-threads?project_id=ops+team&include_archived=true');
      expect(init?.headers).toMatchObject({ Authorization: 'Bearer test-token' });
      return new Response(JSON.stringify([workThread]), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchWorkThreads('http://localhost:8787', 'test-token', { includeArchived: true, projectId: 'ops team' })).resolves.toEqual([workThread]);
  });
});

describe('fetchRecoveryPlan', () => {
  it('fetches the authenticated read-only recovery plan', async () => {
    const plan = { entries: [{ slug: 'garden', status: 'ready', workspace: '/managed/garden' }] };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe('http://localhost:8787/recovery-plan');
      expect(init?.headers).toMatchObject({ Authorization: 'Bearer test-token' });
      return new Response(JSON.stringify(plan), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchRecoveryPlan('http://localhost:8787', 'test-token')).resolves.toEqual(plan);
  });
});

describe('testConnection', () => {
  it('requires authenticated diagnostics instead of unauthenticated health', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe('http://localhost:8787/diagnostics');
      expect(init?.headers).toMatchObject({ Authorization: 'Bearer test-token' });
      return new Response(JSON.stringify({ version: '0.1.0' }), { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(testConnection('http://localhost:8787', 'test-token')).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('rejects when authenticated diagnostics fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('unauthorized', { status: 401 })));

    await expect(testConnection('http://localhost:8787', 'test-token')).rejects.toThrow('API 401');
  });
});
