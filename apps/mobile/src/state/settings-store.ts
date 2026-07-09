import { create, type StoreApi, type UseBoundStore } from 'zustand';

export const defaultApiUrl = 'http://127.0.0.1:8787';

export const settingsStorageKeys = {
  apiUrl: 'hmc.apiUrl',
  apiToken: 'hmc.apiToken',
} as const;

export type SettingsStorage = {
  getItemAsync: (key: string) => Promise<string | null>;
  setItemAsync: (key: string, value: string) => Promise<void>;
};

export type SettingsState = {
  apiUrl: string;
  apiToken: string;
  loaded: boolean;
  load: () => Promise<void>;
  save: (settings: { apiUrl: string; apiToken: string }) => Promise<void>;
};

export function createSettingsStore(storage: SettingsStorage): UseBoundStore<StoreApi<SettingsState>> {
  return create<SettingsState>((set) => ({
    apiUrl: defaultApiUrl,
    apiToken: '',
    loaded: false,
    async load() {
      const [apiUrl, apiToken] = await Promise.all([
        storage.getItemAsync(settingsStorageKeys.apiUrl),
        storage.getItemAsync(settingsStorageKeys.apiToken),
      ]);
      set({
        apiUrl: apiUrl || defaultApiUrl,
        apiToken: apiToken || '',
        loaded: true,
      });
    },
    async save(settings) {
      const next = {
        apiUrl: settings.apiUrl.trim(),
        apiToken: settings.apiToken.trim(),
      };
      await Promise.all([
        storage.setItemAsync(settingsStorageKeys.apiUrl, next.apiUrl),
        storage.setItemAsync(settingsStorageKeys.apiToken, next.apiToken),
      ]);
      set({ ...next, loaded: true });
    },
  }));
}
