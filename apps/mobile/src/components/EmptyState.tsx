import { StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

type Props = { body?: string; title: string };

export function EmptyState({ body, title }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  body: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  container: { backgroundColor: colors.surface, borderRadius: 16, gap: spacing.xs, padding: spacing.md },
  title: { color: colors.text, fontSize: 15, fontWeight: '800' },
});
