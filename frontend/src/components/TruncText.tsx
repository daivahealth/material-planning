/**
 * Middle-truncation text cell — Apple-style.
 * Shows start…end of a string with a dotted underline hint and native tooltip.
 * e.g. "AMOXICILLIN-CAPSULE-500MG-NOVAMOX-" → "AMOXICILLIN-CA…NOVAMOX-"
 */

interface Props {
  text: string
  maxLen?: number   // total display chars before truncating (default 26)
  startLen?: number // chars to keep at start (default 14)
  endLen?: number   // chars to keep at end (default 8)
  style?: React.CSSProperties
  className?: string
  mono?: boolean
}

export function truncateMiddle(text: string, maxLen = 26, startLen = 14, endLen = 8): string {
  if (!text || text.length <= maxLen) return text
  return text.slice(0, startLen) + '…' + text.slice(-endLen)
}

export default function TruncText({ text, maxLen = 26, startLen = 14, endLen = 8, style, className = '', mono }: Props) {
  const display = truncateMiddle(text, maxLen, startLen, endLen)
  const isTruncated = display !== text

  return (
    <span
      title={isTruncated ? text : undefined}
      className={`trunc-text${mono ? ' font-mono' : ''} ${className}`}
      style={style}
      data-truncated={isTruncated || undefined}
    >
      {display}
    </span>
  )
}
