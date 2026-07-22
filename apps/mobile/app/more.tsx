import { Feather } from '@expo/vector-icons';
import { Link } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { bottomNavigationHeight } from '@/navigation/constants';
import { colors, spacing } from '@/theme/tokens';

export default function MoreScreen() {
  const insets = useSafeAreaInsets();

  return <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + bottomNavigationHeight + spacing.xl }]}>
    <Text style={styles.intro}>Connection settings and safe operational review tools.</Text>
    <Link href="/settings" asChild><Pressable accessibilityRole="button" style={({ pressed }) => [styles.card, pressed && styles.pressed]} testID="more-diagnostics">
      <View style={styles.copy}><Text style={styles.title}>Diagnostics</Text><Text style={styles.body}>Review authenticated native project, workspace, bridge, and executor readiness.</Text></View>
      <Feather color={colors.muted} name="chevron-right" size={24} />
    </Pressable></Link>
    <Link href="/recovery-plan" asChild><Pressable accessibilityRole="button" style={({ pressed }) => [styles.card, pressed && styles.pressed]} testID="more-recovery-plan">
      <View style={styles.copy}><Text style={styles.title}>Recovery plan</Text><Text style={styles.body}>Review managed workspaces and their recovery readiness. This view does not make changes.</Text></View>
      <Feather color={colors.muted} name="chevron-right" size={24} />
    </Pressable></Link>
    <Link href="/settings" asChild><Pressable accessibilityRole="button" style={({ pressed }) => [styles.card, pressed && styles.pressed]} testID="more-settings">
      <View style={styles.copy}><Text style={styles.title}>Settings</Text><Text style={styles.body}>Configure the authenticated Control API connection.</Text></View>
      <Feather color={colors.muted} name="chevron-right" size={24} />
    </Pressable></Link>
  </ScrollView>;
}

const styles = StyleSheet.create({ body: { color: colors.muted, fontSize: 14, lineHeight: 20 }, card: { alignItems: 'center', backgroundColor: colors.surface, borderRadius: 18, flexDirection: 'row', gap: spacing.md, padding: spacing.md }, container: { gap: spacing.md, padding: spacing.lg }, copy: { flex: 1, gap: spacing.xs }, intro: { color: colors.muted, fontSize: 14, lineHeight: 20, marginBottom: spacing.sm }, pressed: { opacity: 0.75 }, title: { color: colors.text, fontSize: 17, fontWeight: '800' } });
