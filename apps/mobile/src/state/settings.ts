import * as SecureStore from 'expo-secure-store';

import { createSettingsStore } from './settings-store';

export const useSettingsStore = createSettingsStore(SecureStore);
