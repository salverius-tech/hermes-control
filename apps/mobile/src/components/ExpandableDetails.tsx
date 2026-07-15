import { useState, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

type Props = { children: ReactNode; label: string; initiallyExpanded?: boolean };

export function ExpandableDetails({ children, initiallyExpanded = false, label }: Props) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  return (
    <View style={styles.container}>
      <Pressable accessibilityRole="button" onPress={() => setExpanded((value) => !value)} style={styles.header}>
        <Text style={styles.label}>{label}</Text>
        <Text style={styles.chevron}>{expanded ? '−' : '+'}</Text>
      </Pressable>
      {expanded ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  body: { borderTopColor: colors.border, borderTopWidth: 1, gap: spacing.sm, paddingTop: spacing.md },
  chevron: { color: colors.primary, fontSize: 22, fontWeight: '700' },
  container: { backgroundColor: colors.surface, borderRadius: 16, gap: spacing.sm, padding: spacing.md },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', minHeight: 44 },
  label: { color: colors.text, fontSize: 14, fontWeight: '800' },
});
