import { describe, expect, it } from 'vitest';

import { RecoveryPlanEntry } from '@/api/client';

import { recoveryApplyMessage, recoverableSlugs } from './recovery-plan-state';

const entries: RecoveryPlanEntry[] = [
  { slug: 'ready-one', status: 'ready', workspace: '/managed/one' },
  { slug: 'registered', status: 'already_registered', workspace: '/managed/two' },
  { slug: 'broken', status: 'blocked', workspace: '/managed/three' },
];

describe('recoverableSlugs', () => {
  it('includes only reviewed ready entries with stable slugs', () => {
    expect(recoverableSlugs(entries)).toEqual(['ready-one']);
  });
});

describe('recoveryApplyMessage', () => {
  it('reports per-project restore and blocked results without inferring success', () => {
    expect(recoveryApplyMessage([
      { slug: 'ready-one', status: 'restored' },
      { slug: 'changed', status: 'blocked' },
    ])).toBe('Restored: ready-one. Needs attention: changed.');
  });
});
