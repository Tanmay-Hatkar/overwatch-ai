/**
 * theme.js — single source of truth for color/spacing/radius constants used
 * across the mobile app's screens and components. Previously each file
 * carried its own copy of the same hex literals (#09090b, #f97316, ...),
 * which drifted in small ways (e.g. #1a1a1a vs #18181b for "surface").
 */

export const color = {
  background: '#09090b',
  surface: '#151517',
  surfaceRaised: '#1c1c1f',
  border: '#28282c',
  borderStrong: '#3a3a40',

  textPrimary: '#fafafa',
  textSecondary: '#a1a1aa',
  textMuted: '#71717a',
  onAccent: '#000000',

  accent: '#f97316',
  accentPressed: '#ea6a0c',
  accentMuted: '#7c3f10',

  danger: '#f87171',
  dangerStrong: '#ef4444',
  overdueBorder: '#5c2323',
  overdueTint: 'rgba(239, 68, 68, 0.08)',

  backdrop: 'rgba(0, 0, 0, 0.65)',
}

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 28,
}

export const radius = {
  sm: 8,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
}

export const font = {
  xs: 11,
  sm: 12,
  md: 14,
  lg: 15,
  xl: 17,
  xxl: 22,
}
