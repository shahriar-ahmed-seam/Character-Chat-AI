import Avatar from "./Avatar.jsx";
import { themeFor } from "../theme.js";

// Character picker: renders selectable personas, an empty state, and an error state.
// Pure presentational component — data is supplied by the parent (Requirement 8.8).

export default function CharacterPicker({ personas, loading, error, onSelect, onRetry }) {
  if (loading) {
    return (
      <div className="picker">
        <ul className="persona-list">
          {[0, 1, 2].map((i) => (
            <li key={i} className="persona-card skeleton" aria-hidden="true">
              <span className="skeleton-avatar" />
              <span className="skeleton-lines">
                <span className="skeleton-line" />
                <span className="skeleton-line short" />
              </span>
            </li>
          ))}
        </ul>
        <p className="status" role="status">Loading characters…</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="status error" role="alert">
        <div className="error-emoji">⚠️</div>
        <p>{error}</p>
        <button onClick={onRetry}>Retry</button>
      </div>
    );
  }
  if (!personas || personas.length === 0) {
    // Empty state (Requirement 8.2).
    return (
      <div className="status empty" role="status">
        <div className="empty-emoji">🎭</div>
        <p>No characters are available right now.</p>
      </div>
    );
  }
  return (
    <div className="picker">
      <header className="picker-hero">
        <img className="brand-logo" src="/logo.webp" alt="Character Chat" />
        <p>Pick someone to talk to.</p>
      </header>
      <ul className="persona-list">
        {personas.map((p, i) => {
          const theme = themeFor(p);
          return (
            <li key={p.id} style={{ animationDelay: `${i * 60}ms` }}>
              <button
                className="persona-card"
                onClick={() => onSelect(p)}
                style={{ "--accent": theme.accent, "--accent2": theme.accent2, "--glow": theme.glow }}
              >
                <Avatar persona={p} size={56} />
                <span className="persona-meta">
                  <span className="persona-name">{p.name}</span>
                  <span className="persona-archetype">{p.archetype}</span>
                </span>
                <span className="persona-arrow">→</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
