import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { BottomNavigation } from '@/navigation/BottomNavigation';
import { HeaderSettingsButton } from '@/navigation/HeaderSettingsButton';
import { colors } from '@/theme/tokens';
import { useSettingsStore } from '@/state/settings';

const defaultScreenOptions = {
  headerBackVisible: false,
  headerRight: () => <HeaderSettingsButton />,
};

export default function RootLayout() {
  const loadSettings = useSettingsStore((state) => state.load);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.background },
          headerTintColor: colors.text,
          headerTitleStyle: { fontWeight: '800' },
          contentStyle: { backgroundColor: colors.background },
        }}
      >
        <Stack.Screen name="index" options={{ ...defaultScreenOptions, title: 'Hermes Control' }} />
        <Stack.Screen name="tasks/index" options={{ title: 'Tasks' }} />
        <Stack.Screen name="tasks/[taskId]" options={{ title: 'Task Detail' }} />
        <Stack.Screen name="projects/index" options={{ title: 'Projects' }} />
        <Stack.Screen name="new-task" options={{ title: 'New Task' }} />
        <Stack.Screen name="settings" options={{ headerBackVisible: false, title: 'Settings' }} />
      </Stack>
      <BottomNavigation />
    </SafeAreaProvider>
  );
}
