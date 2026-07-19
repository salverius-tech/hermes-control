import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { BottomNavigation } from '@/navigation/BottomNavigation';
import { HeaderSettingsButton } from '@/navigation/HeaderSettingsButton';
import { colors } from '@/theme/tokens';
import { useSettingsStore } from '@/state/settings';
import { useDataStore } from '@/state/data-store';

const defaultScreenOptions = {
  headerBackVisible: false,
  headerRight: () => <HeaderSettingsButton />,
};

export default function RootLayout() {
  const loadSettings = useSettingsStore((state) => state.load);
  const apiToken = useSettingsStore((state) => state.apiToken);
  const refresh = useDataStore((state) => state.refresh);
  const connect = useDataStore((state) => state.connect);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (!apiToken) return;
    void refresh();
    const stopSocket = connect();
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') void refresh();
    });
    return () => { stopSocket(); subscription.remove(); };
  }, [apiToken, connect, refresh]);

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.background },
          headerTintColor: colors.text,
          headerTitleStyle: { fontWeight: '800' },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.background },
        }}
      >
        <Stack.Screen name="index" options={{ ...defaultScreenOptions, title: 'Hermes Control' }} />
        <Stack.Screen name="tasks/index" options={{ ...defaultScreenOptions, title: 'Tasks' }} />
        <Stack.Screen name="attention" options={{ ...defaultScreenOptions, title: 'Needs Attention' }} />
        <Stack.Screen name="tasks/[taskId]" options={{ title: 'Task Detail' }} />
        <Stack.Screen name="projects/index" options={{ ...defaultScreenOptions, title: 'Projects' }} />
        <Stack.Screen name="projects/manage" options={{ title: 'Manage Project' }} />
        <Stack.Screen name="projects/[projectId]" options={{ title: 'Project' }} />
        <Stack.Screen name="new-task" options={{ ...defaultScreenOptions, title: 'New Task' }} />
        <Stack.Screen name="settings" options={{ headerBackVisible: false, headerRight: undefined, title: 'Settings' }} />
      </Stack>
      <BottomNavigation />
    </SafeAreaProvider>
  );
}
