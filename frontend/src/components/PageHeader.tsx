interface Props {
  title: string
  children?: React.ReactNode
  actions?: React.ReactNode
}
export default function PageHeader({ title, children, actions }: Props) {
  return (
    <div className="mb-6 flex items-start justify-between">
      <div>
        <h1
          className="text-2xl font-bold tracking-tight"
          style={{
            background: 'linear-gradient(90deg, #00d4ff 0%, #a78bfa 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
          }}
        >
          {title}
        </h1>
        {children && (
          <p className="text-sm mt-1" style={{ color: 'var(--c-text-sub)' }}>
            {children}
          </p>
        )}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  )
}
