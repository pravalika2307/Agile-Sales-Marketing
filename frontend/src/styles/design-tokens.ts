/**
 * Agile Sales & Marketing — Centralized Design Tokens
 * 
 * STRICT VISUAL CONSTRAINT:
 * Faithfully matches the visual language and color palette of Agile Receivables:
 * - Primary Accent (Coral/Red): #d7525a
 * - Secondary Accent (Peach/Salmon): #ebad8f
 * - Light Accent Surface (Peach Tint): #fff6f0
 * - Outline/Hover Red: #e45e5e
 * - Header / Deep Navy Text: #09272B
 * - Main Background: #fbf9f7
 * - Surface / Card: #ffffff
 */

export const colors = {
  // Brand & Accents
  primary: "#d7525a",         // Agile coral/red accent
  primaryHover: "#c5444c",    // Darker coral for active/hover
  secondary: "#ebad8f",       // Agile soft peach/salmon
  secondaryLight: "#fff6f0",  // Light peach background tint
  outlineRed: "#e45e5e",      // Border / active ring red

  // Neutrals
  headerNavy: "#09272B",      // Deep navy brand tone
  textPrimary: "#09272B",     // Page titles, headings, primary labels
  textBody: "#1e293b",        // Main readable text (slate-800)
  textSecondary: "#64748b",   // Muted blue-gray for metadata/helpers (slate-500)
  textTertiary: "#94a3b8",    // Subtle placeholders and disabled text (slate-400)

  // Surfaces & Backgrounds
  mainBg: "#fbf9f7",          // Warm off-white minimal background
  cardBg: "#ffffff",          // Pure white card surfaces
  sidebarBg: "#ffffff",       // Clean light sidebar
  headerBg: "#ffffff",        // Clean light header

  // Borders & Dividers
  borderSubtle: "#f1f5f9",    // Ultra-light divider
  borderDefault: "#e2e8f0",   // Clean 1px border (slate-200)
  borderActive: "#d7525a",    // Focused / active border

  // Status Colors (Restrained, consistent)
  status: {
    success: "#10b981",       // Green
    successBg: "#ecfdf5",
    successBorder: "#a7f3d0",

    warning: "#f59e0b",       // Amber
    warningBg: "#fffbeb",
    warningBorder: "#fde68a",

    error: "#d7525a",         // Agile red
    errorBg: "#fff6f0",
    errorBorder: "#fecdd3",

    info: "#0ea5e9",          // Light sky blue
    infoBg: "#f0f9ff",
    infoBorder: "#bae6fd",
  },

  // Chart & Visualization Palette (Agile Family Palette: Coral, Peach, Navy, Slate, Green)
  charts: {
    coral: "#d7525a",
    peach: "#ebad8f",
    navy: "#09272B",
    slate: "#94a3b8",
    green: "#10b981",
    amber: "#f59e0b",
  },
} as const;

export const shadows = {
  sm: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
  card: "0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.03)",
  dropdown: "0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.06)",
  modal: "0 10px 15px -3px rgba(15, 23, 42, 0.1), 0 4px 6px -4px rgba(15, 23, 42, 0.05)",
} as const;

export const radii = {
  sm: "0.375rem",  // 6px - buttons, inputs
  md: "0.5rem",    // 8px - navigation pills
  lg: "0.75rem",   // 12px - cards, dialogs
  xl: "1rem",      // 16px - KPI cards, containers
  full: "9999px",  // badges, pills
} as const;

export const typography = {
  fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
  pageTitle: "text-2xl font-bold tracking-tight text-[#09272B]",
  sectionTitle: "text-lg font-semibold text-[#09272B]",
  body: "text-sm text-[#1e293b]",
  secondary: "text-xs text-[#64748b]",
  kpiNumber: "text-3xl font-bold text-[#09272B] tracking-tight",
} as const;
