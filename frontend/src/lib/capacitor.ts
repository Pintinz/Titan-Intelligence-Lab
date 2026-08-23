import { Capacitor } from '@capacitor/core'

/** Single source of truth for "are we running inside the native Capacitor shell" — every
 * native-specific branch (bottom tabs vs. the existing web drawer, secure storage, native OAuth
 * redirect) reads this instead of importing `@capacitor/core` directly, so there's one place to
 * change if the detection strategy ever needs to. Returns `false` for every web/PWA context
 * (including mobile browsers), which deliberately leaves the existing responsive web nav
 * untouched — only a real native build gets the new bottom-tab chrome. */
export function isNativePlatform(): boolean {
  return Capacitor.isNativePlatform()
}

export function nativePlatform(): 'ios' | 'android' | 'web' {
  return Capacitor.getPlatform() as 'ios' | 'android' | 'web'
}
