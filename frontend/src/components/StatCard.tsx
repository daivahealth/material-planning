interface Props { label: string; value: string | number; sub?: string; color?: string }
export default function StatCard({ label, value, sub, color = 'blue' }: Props) {
  const palette: Record<string, { border: string; glow: string; text: string; bg: string }> = {
    blue:   { border: 'rgba(0,212,255,0.3)',   glow: '0 0 18px rgba(0,212,255,0.15)',   text: 'var(--c-cyan)',   bg: 'rgba(0,212,255,0.08)'   },
    green:  { border: 'rgba(10,255,160,0.3)',  glow: '0 0 18px rgba(10,255,160,0.15)',  text: 'var(--c-green)',  bg: 'rgba(10,255,160,0.08)'  },
    yellow: { border: 'rgba(255,224,75,0.3)',  glow: '0 0 18px rgba(255,224,75,0.15)',  text: 'var(--c-yellow)', bg: 'rgba(255,224,75,0.08)'  },
    red:    { border: 'rgba(255,37,96,0.3)',   glow: '0 0 18px rgba(255,37,96,0.15)',   text: 'var(--c-red)',    bg: 'rgba(255,37,96,0.08)'   },
    purple: { border: 'rgba(167,139,250,0.3)', glow: '0 0 18px rgba(167,139,250,0.15)', text: 'var(--c-purple)', bg: 'rgba(167,139,250,0.08)' },
  }
  const p = palette[color] || palette.blue
  return (
    <div
      className="rounded-xl p-4 relative overflow-hidden"
      style={{
        background: `linear-gradient(135deg, ${p.bg}, var(--c-panel-to, rgba(5,9,15,0.9)))`,
        border: `1px solid ${p.border}`,
        boxShadow: p.glow,
      }}
    >
      {/* corner accent */}
      <div
        className="absolute top-0 right-0 w-16 h-16 rounded-bl-full opacity-10"
        style={{ background: p.text }}
      />
      <p
        className="text-xs font-bold uppercase tracking-widest mb-2"
        style={{ color: p.text, opacity: 0.75 }}
      >
        {label}
      </p>
      <p
        className="text-3xl font-bold"
        style={{ color: p.text }}
      >
        {value}
      </p>
      {sub && (
        <p className="text-xs mt-1" style={{ color: 'var(--c-text-sub)' }}>{sub}</p>
      )}
    </div>
  )
}
