import { Pressable, StyleSheet } from 'react-native';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';

export const bookmarkIcon = '<svg width="20" height="22" viewBox="0 0 20 22" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 1H17C18.1 1 19 1.9 19 3V21L10 17L1 21V3C1 1.9 1.9 1 3 1Z" fill="white"/></svg>';

export function BookmarkButton({ disabled = false, isSaved, onPress }: {
  disabled?: boolean;
  isSaved: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityLabel={isSaved ? 'Remove saved site' : 'Save site'}
      accessibilityRole="button"
      accessibilityState={{ disabled, selected: isSaved }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.button, isSaved ? styles.saved : styles.unsaved, disabled && styles.disabled]}
    >
      <SvgAssetIcon height={22} svg={bookmarkIcon} width={20} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { alignItems: 'center', borderRadius: 22, height: 44, justifyContent: 'center', width: 44 },
  saved: { backgroundColor: '#1687F8' },
  unsaved: { backgroundColor: '#8C969D' },
  disabled: { opacity: 0.65 }
});
