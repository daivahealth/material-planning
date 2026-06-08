import { Check, X } from 'lucide-react'

export const PASSWORD_RULES = [
  { label: 'At least 8 characters',      test: (p: string) => p.length >= 8 },
  { label: '1 uppercase letter (A–Z)',    test: (p: string) => /[A-Z]/.test(p) },
  { label: '1 number (0–9)',              test: (p: string) => /[0-9]/.test(p) },
  { label: '1 special character (!@#…)', test: (p: string) => /[^a-zA-Z0-9]/.test(p) },
]

export function isPasswordValid(pwd: string): boolean {
  return PASSWORD_RULES.every(r => r.test(pwd))
}

export function PasswordStrength({ password }: { password: string }) {
  if (!password) return null
  return (
    <ul className="mt-1.5 space-y-0.5">
      {PASSWORD_RULES.map(r => {
        const ok = r.test(password)
        return (
          <li
            key={r.label}
            className="flex items-center gap-1.5 text-xs"
            style={{ color: ok ? 'var(--c-green)' : 'var(--c-red)' }}
          >
            {ok
              ? <Check size={10} strokeWidth={3} />
              : <X    size={10} strokeWidth={3} />}
            {r.label}
          </li>
        )
      })}
    </ul>
  )
}
