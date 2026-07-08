import { describe, expect, it } from 'vitest';

import { buildApiUrl, buildWebSocketUrl } from './url';

describe('buildApiUrl', () => {
  it('joins base URLs and paths without duplicate slashes', () => {
    expect(buildApiUrl('http://localhost:8787/', '/tasks')).toBe('http://localhost:8787/tasks');
  });

  it('accepts paths without a leading slash', () => {
    expect(buildApiUrl('http://localhost:8787', 'health')).toBe('http://localhost:8787/health');
  });

  it('keeps query strings intact when paths include request parameters', () => {
    expect(buildApiUrl('http://localhost:8787/', '/tasks?limit=10')).toBe(
      'http://localhost:8787/tasks?limit=10',
    );
  });
});

describe('buildWebSocketUrl', () => {
  it('converts http API origins to ws event URLs with encoded token', () => {
    expect(buildWebSocketUrl('http://localhost:8787/', 'dev token')).toBe(
      'ws://localhost:8787/ws/events?token=dev%20token',
    );
  });

  it('converts https API origins to secure websocket URLs', () => {
    expect(buildWebSocketUrl('https://hermes.local', 'token')).toBe('wss://hermes.local/ws/events?token=token');
  });

  it('rejects blank API origins instead of building a relative websocket URL', () => {
    expect(() => buildWebSocketUrl('   ', 'token')).toThrow();
  });
});
