// Per-character visual theming. Presentation lives in the client (thin-client rule:
// no business logic here, just look-and-feel). Known characters get hand-picked
// palettes + emoji; unknown ones get a deterministic palette derived from their id,
// so any persona the backend adds still looks intentional.

const KNOWN = {
  elias: { accent: "#8a7dff", accent2: "#4a3aa8", emoji: "🕵️", glow: "#6c5cffaa" },
  luna: { accent: "#5fd0ff", accent2: "#2a7fd6", emoji: "🌙", glow: "#5fd0ffaa" },
  sergeant_kane: { accent: "#ff8a5c", accent2: "#c2452a", emoji: "🎖️", glow: "#ff7a4baa" },
};

const FALLBACK_PALETTES = [
  { accent: "#ff8ab4", accent2: "#c23a6b", emoji: "✨" },
  { accent: "#7CE7B0", accent2: "#1f9d6b", emoji: "🌿" },
  { accent: "#ffd166", accent2: "#c79100", emoji: "⭐" },
  { accent: "#9b8cff", accent2: "#5b3fd6", emoji: "🔮" },
  { accent: "#67e8f9", accent2: "#0e90a8", emoji: "💠" },
];

function hashString(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export function themeFor(persona) {
  if (!persona) return FALLBACK_PALETTES[0];
  if (KNOWN[persona.id]) return KNOWN[persona.id];
  const palette = FALLBACK_PALETTES[hashString(persona.id) % FALLBACK_PALETTES.length];
  return { glow: `${palette.accent}aa`, ...palette };
}

export function initials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
