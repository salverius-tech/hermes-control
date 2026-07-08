export function appendTranscript(currentPrompt: string, transcript: string): string {
  const next = transcript.trim();
  if (!next) return currentPrompt;

  const current = currentPrompt.trim();
  return current ? `${current}\n${next}` : next;
}
