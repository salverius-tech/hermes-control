import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

type Props = { label: string; value?: string | null };

export function MetadataRow({ label, value }: Props) {
  if (!value) return null;
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text numberOfLines={1} style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  label: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' },
  row: { alignItems: 'center', flexDirection: 'row', gap: spacing.md, justifyContent: 'space-between', minHeight: 28 },
  value: { color: colors.text, flex: 1, fontSize: 14, textAlign: 'right' },
});
