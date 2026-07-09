import { describe, expect, it } from 'vitest';

import { createSettingsStore, defaultApiUrl, settingsStorageKeys, type SettingsStorage } from './settings-store';

function memoryStorage(seed: Record<string, string | null> = {}) {
  const writes: Array<[string, string]> = [];
  const values = new Map(Object.entries(seed));
  const storage: SettingsStorage = {
    async getItemAsync(key) {
      return values.get(key) ?? null;
    },
    async setItemAsync(key, value) {
      writes.push([key, value]);
      values.set(key, value);
    },
  };
  return { storage, writes, values };
}

describe('createSettingsStore', () => {
  it('loads secure settings when both values exist', async () => {
    const { storage } = memoryStorage({
      [settingsStorageKeys.apiUrl]: 'http://192.168.1.10:8787',
      [settingsStorageKeys.apiToken]: 'secret-token',
    });
    const store = createSettingsStore(storage);

    await store.getState().load();

    expect(store.getState()).toMatchObject({
      apiUrl: 'http://192.168.1.10:8787',
      apiToken: 'secret-token',
      loaded: true,
    });
  });

  it('falls back to safe defaults when secure storage is empty', async () => {
    const { storage } = memoryStorage();
    const store = createSettingsStore(storage);

    await store.getState().load();

    expect(store.getState()).toMatchObject({ apiUrl: defaultApiUrl, apiToken: '', loaded: true });
  });

  it('trims and persists settings through secure storage', async () => {
    const { storage, writes } = memoryStorage();
    const store = createSettingsStore(storage);

    await store.getState().save({ apiUrl: '  http://host:8787  ', apiToken: '  token  ' });

    expect(writes).toEqual([
      [settingsStorageKeys.apiUrl, 'http://host:8787'],
      [settingsStorageKeys.apiToken, 'token'],
    ]);
    expect(store.getState()).toMatchObject({ apiUrl: 'http://host:8787', apiToken: 'token', loaded: true });
  });
});
