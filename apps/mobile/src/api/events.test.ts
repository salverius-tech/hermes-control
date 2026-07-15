import { describe, expect, it } from 'vitest';

import { redactWebSocketUrl } from './events';

describe('redactWebSocketUrl', () => {
  it('redacts only the token query value', () => {
    expect(redactWebSocketUrl('ws://localhost:8787/ws/events?token=secret%20value')).toBe(
      'ws://localhost:8787/ws/events?token=[REDACTED]',
    );
  });

  it('preserves other query parameters', () => {
    expect(redactWebSocketUrl('ws://localhost:8787/ws/events?token=secret&client=android')).toBe(
      'ws://localhost:8787/ws/events?token=[REDACTED]&client=android',
    );
  });
});
