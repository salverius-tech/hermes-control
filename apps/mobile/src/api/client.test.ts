import { describe, expect, it, vi } from 'vitest';

import { testConnection } from './client';

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
