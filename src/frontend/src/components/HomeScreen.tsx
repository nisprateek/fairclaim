import { AlertTriangle, Scale, Send } from 'lucide-react'
import { sampleStory } from '../sample'

// The whole homescreen is one prompt box (gemini.google.com / claude.ai
// style): headline, textarea, send FAB, and one sample-story helper.
// Everything else waits until the user has started a case.
export function HomeScreen({
  story,
  onStoryChange,
  onStart,
  busy,
  error,
}: {
  story: string
  onStoryChange: (value: string) => void
  onStart: () => void
  busy: boolean
  error: string | null
}) {
  const canStart = !busy && story.trim().length > 0

  return (
    <section className="home">
      <span className="home-badge">
        <Scale size={15} /> UK Consumer Rights Act 2015
      </span>
      <h1>
        What went wrong with your&nbsp;purchase?
      </h1>

      <div className="prompt-wrap">
        <span className="prompt-halo" aria-hidden="true" />
        <form
          className="prompt-shell"
          onSubmit={(event) => {
            event.preventDefault()
            if (canStart) onStart()
          }}
        >
          <textarea
            value={story}
            onChange={(event) => onStoryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                if (canStart) onStart()
              }
            }}
            placeholder="I bought a laptop from TechBarn 20 days ago for £600 and it now randomly shuts down. Their website says 'All sales are final - no refunds.' I just want my money back."
            rows={3}
            disabled={busy}
            ref={(element) => element?.focus({ preventScroll: true })}
            aria-label="Describe the purchase problem"
          />
          <div className="prompt-toolbar">
            <span className="prompt-hint">Shift + Enter for a new line</span>
            <button type="submit" className="send-fab" disabled={!canStart} aria-label="Start the case">
              <Send size={19} />
            </button>
          </div>
        </form>
      </div>

      <div className="prompt-chips">
        <button type="button" onClick={() => onStoryChange(sampleStory)} disabled={busy}>
          Use the sample story
        </button>
      </div>

      {error && (
        <div className="error-banner" role="alert">
          <AlertTriangle size={18} />
          <p>{error}</p>
        </div>
      )}

      <p className="home-disclaimer">
        General information about the Consumer Rights Act 2015 — not advice from a solicitor.
      </p>
    </section>
  )
}
