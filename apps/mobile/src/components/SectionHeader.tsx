import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '@/theme/tokens';

type Props = {
  actionHref?: string;
  actionLabel?: string;
  count?: number;
  title: string;
};

export function SectionHeader({ actionHref, actionLabel, count, title }: Props) {
  const content = (
    <View style={styles.row}>
      <View style={styles.titleRow}>
        <Text style={styles.title}>{title}</Text>
        {count !== undefined ? <Text style={styles.count}>{count}</Text> : null}
      </View>
      {actionHref && actionLabel ? <Text style={styles.action}>{actionLabel}</Text> : null}
    </View>
  );

  return actionHref && actionLabel ? <Link href={actionHref as never} asChild><Pressable accessibilityRole="button">{content}</Pressable></Link> : content;
}

const styles = StyleSheet.create({
  action: { color: colors.primary, fontSize: 14, fontWeight: '800' },
  count: { backgroundColor: colors.primarySoft, borderRadius: 999, color: colors.text, fontSize: 12, fontWeight: '800', minWidth: 24, overflow: 'hidden', paddingHorizontal: spacing.sm, paddingVertical: 3, textAlign: 'center' },
  row: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', minHeight: 44 },
  title: { color: colors.text, fontSize: 18, fontWeight: '900' },
  titleRow: { alignItems: 'center', flexDirection: 'row', gap: spacing.sm },
});
