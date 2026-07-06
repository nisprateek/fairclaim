import { useEffect, useState } from 'react'
import { Check, Sparkles } from 'lucide-react'

// A claude.ai-style live activity feed: steps reveal one at a time on a
// timer while a request is in flight, the current one pulsing, finished
// ones ticked. The backend runs each turn as a single call, so the cadence
// is client-side pacing — the last step simply holds until the reply lands
// and the parent unmounts this component.
export interface ActivityScript {
  title: string
  steps: string[]
  /** ms between step reveals; the last revealed step holds until unmount */
  interval?: number
}

export const INITIAL_ACTIVITY: ActivityScript = {
  title: 'Reading your story',
  steps: [
    'Checking this is a UK consumer-goods case',
    'Pulling the seller, product and fault from your words',
    'Filling in the case file',
    'Choosing the one question worth asking next',
  ],
  interval: 2100,
}

export const TURN_ACTIVITY: ActivityScript = {
  title: 'Thinking',
  steps: [
    'Saving your answer to the case file',
    'Re-checking what is still missing',
    'Choosing the next question',
  ],
  interval: 1300,
}

export const ANALYSIS_ACTIVITY: ActivityScript = {
  title: 'Building your case',
  steps: [
    'Reading the small print for unfair terms',
    'Matching the fault to the remedy ladder in the Consumer Rights Act 2015',
    'Drafting your complaint letter in three tones',
  ],
  interval: 3200,
}

export function AgentActivity({ activity }: { activity: ActivityScript }) {
  const { title, steps } = activity
  const interval = activity.interval ?? 1600
  const [revealed, setRevealed] = useState(1)

  useEffect(() => {
    if (revealed >= steps.length) return
    const timer = window.setTimeout(() => setRevealed((count) => count + 1), interval)
    return () => window.clearTimeout(timer)
  }, [revealed, steps.length, interval])

  return (
    <section className="agent-activity" role="status" aria-live="polite">
      <header>
        <span className="activity-icon" aria-hidden="true">
          <Sparkles size={15} />
        </span>
        <strong className="shimmer-text">{title}…</strong>
      </header>
      <ol>
        {steps.slice(0, revealed).map((step, index) => {
          const isCurrent = index === revealed - 1
          return (
            <li key={step} className={isCurrent ? 'current' : 'done'}>
              <span className="step-marker" aria-hidden="true">
                {isCurrent ? <span className="step-pulse" /> : <Check size={13} strokeWidth={3} />}
              </span>
              <span>{step}</span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
