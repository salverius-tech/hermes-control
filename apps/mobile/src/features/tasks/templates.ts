export type PromptTemplate = {
  id: string;
  label: string;
  prompt: string;
};

export const promptTemplates: PromptTemplate[] = [
  {
    id: 'review-changes',
    label: 'Review changes',
    prompt: 'Review the current git changes, identify risks, and suggest focused fixes without making unrelated edits.',
  },
  {
    id: 'run-tests',
    label: 'Run tests',
    prompt: 'Run the relevant tests, diagnose any failures, fix root causes, and report the exact verification output.',
  },
  {
    id: 'summarize-repo',
    label: 'Summarize repo',
    prompt: 'Inspect the repository structure and summarize the architecture, key workflows, and verification commands.',
  },
];

export function applyPromptTemplate(currentPrompt: string, templatePrompt: string): string {
  const current = currentPrompt.trim();
  const template = templatePrompt.trim();
  if (!current) return template;
  if (!template) return current;
  return `${current}\n\n${template}`;
}
