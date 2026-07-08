import { describe, expect, it } from 'vitest';

import { appendTranscript } from './prompt';

describe('appendTranscript', () => {
  it('uses the transcript as the prompt when the current prompt is blank', () => {
    expect(appendTranscript('   ', '  Check Hermes status  ')).toBe('Check Hermes status');
  });

  it('appends final voice text on a new line without losing the typed prompt', () => {
    expect(appendTranscript('Review running tasks', 'Start the next task')).toBe(
      'Review running tasks\nStart the next task',
    );
  });

  it('keeps the current prompt unchanged when speech returns no text', () => {
    expect(appendTranscript('Review running tasks', '   ')).toBe('Review running tasks');
  });

  it('does not preserve accidental leading or trailing whitespace from the typed prompt', () => {
    expect(appendTranscript('  Review running tasks  ', '  Start the next task  ')).toBe(
      'Review running tasks\nStart the next task',
    );
  });
});
