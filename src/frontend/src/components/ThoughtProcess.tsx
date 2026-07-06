import { useState } from 'react'
import { Check, ChevronDown, Sparkles, User } from 'lucide-react'
import type { TraceEntry } from '../lib/trace'

// Collapsible plain-language trace of everything the agent has done so far —
// the user's words, the work in between, and each question or verdict.
export function ThoughtProcess({ trace }: { trace: TraceEntry[] }) {
  const [open, setOpen] = useState(false)
  if (trace.length === 0) return null

  return (
    <section className="thought-process">
      <button
        type="button"
        className="thought-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <Sparkles size={16} />
        <span>Thought process</span>
        <small>{trace.length} steps</small>
        <ChevronDown size={16} className={`chevron ${open ? 'flipped' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <ol className="trace-list">
          {trace.map((entry, index) => (
            <li className={`trace-entry trace-${entry.kind}`} key={`${entry.label}-${index}`}>
              <span className="trace-marker" aria-hidden="true">
                {entry.kind === 'user' ? (
                  <User size={12} />
                ) : entry.kind === 'step' ? (
                  <Check size={12} strokeWidth={3} />
                ) : (
                  <Sparkles size={12} />
                )}
              </span>
              <div>
                <p>{entry.label}</p>
                {entry.detail && <small>{entry.detail}</small>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
