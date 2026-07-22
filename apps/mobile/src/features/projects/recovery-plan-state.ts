import type { RecoveryApplyResult, RecoveryPlanEntry } from '@/api/client';

/** Only a fresh, read-only plan entry marked ready can be submitted for restore. */
export function recoverableSlugs(entries: RecoveryPlanEntry[]): string[] {
  return entries.flatMap((entry) => entry.status === 'ready' && entry.slug ? [entry.slug] : []);
}

export function recoveryApplyMessage(results: RecoveryApplyResult[]): string {
  const restored = results.filter((result) => result.status === 'restored').map((result) => result.slug);
  const blocked = results.filter((result) => result.status === 'blocked').map((result) => result.slug);
  return [
    restored.length ? `Restored: ${restored.join(', ')}.` : '',
    blocked.length ? `Needs attention: ${blocked.join(', ')}.` : '',
  ].filter(Boolean).join(' ');
}
