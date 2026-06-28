import { useState } from "react";
import { themeFor, initials } from "../theme.js";

// Avatar: uses a real portrait from /avatars/<id>.{webp,png,jpg} if you drop one in,
// otherwise renders a polished gradient disc with the character's initials.
// Add images to web/public/avatars/ named by persona id (e.g. luna.webp).
export default function Avatar({ persona, size = 48 }) {
  const [imgFailed, setImgFailed] = useState(false);
  const theme = themeFor(persona);
  const src = `/avatars/${persona.id}.webp`;
  const dim = { width: size, height: size, minWidth: size };

  if (!imgFailed) {
    return (
      <img
        className="avatar avatar-img"
        style={{ ...dim, "--glow": theme.glow }}
        src={src}
        alt={persona.name}
        onError={() => setImgFailed(true)}
      />
    );
  }

  return (
    <span
      className="avatar avatar-fallback"
      style={{
        ...dim,
        background: `linear-gradient(135deg, ${theme.accent}, ${theme.accent2})`,
        fontSize: size * 0.4,
        "--glow": theme.glow,
      }}
      aria-hidden="true"
    >
      <span className="avatar-emoji" style={{ fontSize: size * 0.5 }}>
        {theme.emoji}
      </span>
      <span className="avatar-initials">{initials(persona.name)}</span>
    </span>
  );
}
