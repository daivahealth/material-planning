/**
 * Environment ribbon — a diagonal corner banner naming the instance (UAT, DEV…).
 *
 * Renders ONLY when VITE_ENV_RIBBON is set. Like the other VITE_* values it is
 * baked into the bundle at image-build time, so each environment's image
 * carries its own label and production (which sets nothing) shows no ribbon.
 *
 * Purely decorative: aria-hidden and pointer-events:none, so it never blocks a
 * click or is announced by a screen reader.
 */
const LABEL = (import.meta.env.VITE_ENV_RIBBON ?? '').trim()
// `|| default`, not `?? default`: an unset build arg arrives as an empty
// string, which is not nullish — `??` would leave the colour blank and the
// band invisible.
//
// Inverted scheme: a LIGHT band with DARK text, which stands out far better
// against this app's dark theme than white-on-orange did.
const COLOR = ((import.meta.env.VITE_ENV_RIBBON_COLOR ?? '').trim()) || '#f5c9a8'
const TEXT_COLOR = ((import.meta.env.VITE_ENV_RIBBON_TEXT_COLOR ?? '').trim()) || '#7a3b12'

export default function EnvRibbon() {
  if (!LABEL) return null

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: 170,
        height: 170,
        overflow: 'hidden',
        pointerEvents: 'none',
        zIndex: 9999,
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 40,
          left: -62,
          width: 240,
          padding: '7px 0',
          transform: 'rotate(-45deg)',
          background: COLOR,
          color: TEXT_COLOR,
          textAlign: 'center',
          fontSize: '0.8125rem',
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          boxShadow: '0 2px 8px rgba(0,0,0,0.45)',
        }}
      >
        {LABEL}
      </div>
    </div>
  )
}
