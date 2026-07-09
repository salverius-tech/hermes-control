import { describe, expect, it } from 'vitest';

import { applyPromptTemplate, promptTemplates } from './templates';

describe('prompt templates', () => {
  it('defines common non-empty task templates', () => {
    expect(promptTemplates.length).toBeGreaterThanOrEqual(3);
    for (const template of promptTemplates) {
      expect(template.label.trim()).not.toBe('');
      expect(template.prompt.trim()).not.toBe('');
    }
  });

  it('replaces a blank prompt with the template text', () => {
    expect(applyPromptTemplate('   ', 'Run the tests')).toBe('Run the tests');
  });

  it('appends a template to an existing prompt with spacing', () => {
    expect(applyPromptTemplate('Review this branch.', 'Focus on security.')).toBe('Review this branch.\n\nFocus on security.');
  });
});
