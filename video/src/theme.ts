import { Easing } from "remotion";

export const theme = {
  colors: {
    bg: "#07090E",
    bgCard: "rgba(15, 23, 42, 0.75)",
    bgCardBorder: "rgba(255, 255, 255, 0.12)",
    primary: "#F59E0B", // CaiSheng Imperial Gold / Amber
    primaryGlow: "rgba(245, 158, 11, 0.35)",
    accentCyan: "#06B6D4",
    accentGreen: "#10B981",
    accentRed: "#EF4444",
    accentPurple: "#8B5CF6",
    text: "#F8FAFC",
    textMuted: "#94A3B8",
    textDim: "#64748B",
    border: "rgba(255, 255, 255, 0.08)",
  },
  fonts: {
    display: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', Menlo, monospace",
  },
  ease: {
    out: Easing.bezier(0.16, 1, 0.3, 1),      // easeOutExpo
    inOut: Easing.bezier(0.83, 0, 0.17, 1),   // easeInOutQuint
    in: Easing.bezier(0.7, 0, 0.84, 0),       // exits
  },
  spring: {
    snappy: { damping: 14, stiffness: 160, mass: 0.6 },
    smooth: { damping: 20, stiffness: 90, mass: 1 },
    bouncy: { damping: 11, stiffness: 170, mass: 0.7 },
  },
} as const;
