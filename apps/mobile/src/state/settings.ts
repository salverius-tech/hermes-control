import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

const API_URL_KEY = 'hmc.apiUrl';
const API_TOKEN_KEY = 'hmc.apiToken';

type SettingsState = {
  apiUrl: string;
  apiToken: string;
  loaded: boolean;
  load: () => Promise<void>;
  save: (settings: { apiUrl: string; apiToken: string }) => Promise<void>;
};

export const useSettingsStore = create<SettingsState>((set) => ({
  apiUrl: 'http://127.0.0.1:8787',
  apiToken: '',
  loaded: false,
  async load() {
    const [apiUrl, apiToken] = await Promise.all([
      SecureStore.getItemAsync(API_URL_KEY),
      SecureStore.getItemAsync(API_TOKEN_KEY),
    ]);
    set({
      apiUrl: apiUrl || 'http://127.0.0.1:8787',
      apiToken: apiToken || '',
      loaded: true,
    });
  },
  async save(settings) {
    await Promise.all([
      SecureStore.setItemAsync(API_URL_KEY, settings.apiUrl),
      SecureStore.setItemAsync(API_TOKEN_KEY, settings.apiToken),
    ]);
    set({ ...settings, loaded: true });
  },
}));
