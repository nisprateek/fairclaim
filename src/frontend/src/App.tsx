import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, RefreshCcw } from 'lucide-react'
import { newId, sendTurn } from './api'
import {
  ANALYSIS_ACTIVITY,
  AgentActivity,
  INITIAL_ACTIVITY,
  TURN_ACTIVITY,
  type ActivityScript,
} from './components/AgentActivity'
import { HomeScreen } from './components/HomeScreen'
import { CaseFile, GeneratedCard, ScopeGateCard } from './components/IntakeCards'
import { ResultsDashboard } from './components/ResultsDashboard'
import { ThoughtProcess } from './components/ThoughtProcess'
import {
  NO_TERMS_ANSWER,
  TERMS_FALLBACK,
  countKnownFields,
  fieldConfig,
  fieldTitle,
  labelRemedy,
} from './lib/case'
import type { TraceEntry } from './lib/trace'
import type {
  CaseFields,
  EmailDraft,
  IntakeTurn,
  RemedyResult,
  ResultBundle,
  TcAnalysisResult,
} from './types'
import './App.css'

type Stage = 'start' | 'interview' | 'analysing' | 'results'

function summariseAnswer(answer: string) {
  if (answer === NO_TERMS_ANSWER) return 'No terms available — continue on statutory rights alone'
  if (answer.length > 160) return `${answer.slice(0, 157)}…`
  return answer
}

// Turn the intake reply into plain-language trace entries.
function traceForTurn(turn: IntakeTurn, isOpening: boolean): TraceEntry[] {
  if (turn.scope_gate_failure) {
    return [
      { kind: 'agent', label: 'Stopped — outside the scope of this tool', detail: turn.scope_gate_failure },
    ]
  }
  const entries: TraceEntry[] = []
  if (isOpening) {
    entries.push({ kind: 'step', label: 'Confirmed this looks like a UK consumer-goods case' })
    entries.push({
      kind: 'step',
      label: `Pre-filled ${countKnownFields(turn.collected_fields)} of ${fieldConfig.length} case facts from your story`,
    })
  }
  const component = turn.next_component
  if (component) {
    entries.push({
      kind: 'agent',
      label: `Asked about ${fieldTitle(component.field).toLowerCase()}`,
      detail: component.prompt,
    })
  } else if (turn.is_complete) {
    entries.push({
      kind: 'agent',
      label: "Intake complete — asked for the seller's terms",
      detail: TERMS_FALLBACK.prompt,
    })
  }
  return entries
}

function traceForResults(bundle: ResultBundle): TraceEntry[] {
  const clauseCount = bundle.tc.clauses.length
  return [
    {
      kind: 'step',
      label: bundle.termsProvided
        ? `Reviewed ${clauseCount} clause${clauseCount === 1 ? '' : 's'} from the seller's terms`
        : 'No terms provided — your statutory rights apply regardless',
    },
    {
      kind: 'step',
      label: `Placed the fault on the remedy ladder (${bundle.remedy.statutory_basis.join(', ')})`,
    },
    {
      kind: 'step',
      label: `Drafted ${bundle.emails.length} letter${bundle.emails.length === 1 ? '' : 's'} — each in polite, firm and formal tones`,
    },
    {
      kind: 'agent',
      label: `Best-supported remedy: ${labelRemedy(bundle.remedy.primary_remedy)}`,
      detail: bundle.remedy.simple_explanation,
    },
  ]
}

function App() {
  const [stage, setStage] = useState<Stage>('start')
  const [story, setStory] = useState('')
  const [sessionIds, setSessionIds] = useState(() => ({
    userId: newId('user'),
    sessionId: newId('session'),
  }))
  const [turn, setTurn] = useState<IntakeTurn | null>(null)
  const [fields, setFields] = useState<CaseFields>({})
  const [trace, setTrace] = useState<TraceEntry[]>([])
  const [results, setResults] = useState<ResultBundle | null>(null)
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState<ActivityScript | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Each stage is a fresh surface — don't carry the scroll offset across.
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [stage])

  const activeComponent = useMemo(() => {
    if (turn?.scope_gate_failure) return null
    return turn?.next_component ?? (turn?.is_complete ? TERMS_FALLBACK : null)
  }, [turn])

  const progress = Math.round((countKnownFields(fields) / fieldConfig.length) * 100)

  const caseTitle = useMemo(() => {
    const parts = [fields.product, fields.seller_name].filter(
      (part): part is string => typeof part === 'string' && part.length > 0,
    )
    return parts.join(' · ') || 'Building your case'
  }, [fields.product, fields.seller_name])

  function beginCase(openingStory: string) {
    setError(null)
    setResults(null)
    setTurn(null)
    setFields({})
    setTrace([{ kind: 'user', label: 'You described the problem', detail: openingStory }])
    setStage('interview')
    setBusy(true)
  }

  async function startLive() {
    const trimmed = story.trim()
    if (!trimmed) return
    const nextIds = { userId: newId('user'), sessionId: newId('session') }
    setSessionIds(nextIds)
    beginCase(trimmed)
    setActivity(INITIAL_ACTIVITY)
    try {
      const state = await sendTurn(nextIds.userId, nextIds.sessionId, trimmed, true)
      const next = ingestTurnState(state)
      setTrace((entries) => [...entries, ...traceForTurn(next, true)])
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
    } finally {
      setBusy(false)
      setActivity(null)
    }
  }

  function ingestTurnState(state: Record<string, unknown>): IntakeTurn {
    const next = state.intake_turn as IntakeTurn | undefined
    if (!next) throw new Error('Backend did not return an intake_turn. Check the backend logs.')
    setTurn(next)
    setFields(next.collected_fields ?? {})
    return next
  }

  async function submitAnswer(answer: string, stateDelta?: Record<string, unknown>) {
    const component = activeComponent
    if (!component) return
    setError(null)
    setTrace((entries) => [...entries, { kind: 'user', label: 'You answered', detail: summariseAnswer(answer) }])

    // Submitting terms (or explicitly going without them) triggers the whole
    // analysis pipeline in this same /run call — show the analysis activity.
    const isTermsStep = component.field === 'terms_source'
    setBusy(true)
    setActivity(isTermsStep ? ANALYSIS_ACTIVITY : TURN_ACTIVITY)
    if (isTermsStep) setStage('analysing')
    try {
      const state = await sendTurn(sessionIds.userId, sessionIds.sessionId, answer, false, stateDelta)
      const next = ingestTurnState(state)
      const tcResult = state.tc_analysis_result as TcAnalysisResult | undefined
      const remedyResult = state.remedy_result as RemedyResult | undefined
      const emailDrafts = state.email_drafts as EmailDraft[] | undefined
      if (tcResult && remedyResult && emailDrafts) {
        const bundle: ResultBundle = {
          tc: tcResult,
          remedy: remedyResult,
          emails: emailDrafts,
          termsProvided: next.collected_fields?.terms_source !== 'none',
        }
        setResults(bundle)
        setTrace((entries) => [...entries, ...traceForResults(bundle)])
        setStage('results')
      } else {
        setTrace((entries) => [...entries, ...traceForTurn(next, false)])
        // Intake still had gaps — back to the interview rather than a stuck
        // analysing screen.
        if (isTermsStep) setStage('interview')
      }
    } catch (e) {
      setError(String(e instanceof Error ? e.message : e))
      if (isTermsStep) setStage('interview')
    } finally {
      setBusy(false)
      setActivity(null)
    }
  }

  function reset() {
    setStage('start')
    setStory('')
    setTurn(null)
    setFields({})
    setTrace([])
    setResults(null)
    setBusy(false)
    setActivity(null)
    setError(null)
    setSessionIds({ userId: newId('user'), sessionId: newId('session') })
  }

  const showWorkspace = stage === 'interview' || stage === 'analysing'

  return (
    <>
      <div className="bg-ornaments" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>

      <nav className="top-nav" aria-label="Product navigation">
        <div className="nav-inner">
          <div className="brand">
            <img className="brand-logo" src="/fairclaimai-logo.png" alt="FairClaimAI" />
          </div>
          <div className="nav-actions">
            {stage !== 'start' && (
              <button
                type="button"
                className="ghost-action"
                onClick={reset}
                aria-label="Start a new case"
                title="Start a new case"
              >
                <RefreshCcw size={16} /> <span className="nav-action-label">New case</span>
              </button>
            )}
          </div>
        </div>
      </nav>

      <main className="app-shell">
        {stage === 'start' ? (
          <HomeScreen
            story={story}
            onStoryChange={setStory}
            onStart={() => void startLive()}
            busy={busy}
            error={error}
          />
        ) : stage === 'results' && results ? (
          <ResultsDashboard results={results} trace={trace} />
        ) : showWorkspace ? (
          <section className="workspace">
            <header className="case-strip">
              <div>
                <span>Case</span>
                <strong>{caseTitle}</strong>
              </div>
            </header>

            <div className="workspace-grid">
              <div className="workspace-main">
                {busy && activity && <AgentActivity key={trace.length} activity={activity} />}

                {!busy && error && (
                  <div className="error-banner" role="alert">
                    <AlertTriangle size={18} />
                    <div>
                      <p>{error}</p>
                      {!turn && (
                        <button
                          type="button"
                          className="secondary-action"
                          onClick={() => {
                            setError(null)
                            setStage('start')
                          }}
                        >
                          Edit your story
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {!busy && stage === 'interview' && turn?.scope_gate_failure && (
                  <ScopeGateCard message={turn.scope_gate_failure} onReset={reset} />
                )}

                {!busy && stage === 'interview' && !turn?.scope_gate_failure && activeComponent && (
                  <GeneratedCard
                    key={`${activeComponent.field}-${activeComponent.type}`}
                    component={activeComponent}
                    busy={busy}
                    onAnswer={(answer, stateDelta) => void submitAnswer(answer, stateDelta)}
                  />
                )}

                <ThoughtProcess trace={trace} />
              </div>

              <CaseFile fields={fields} progress={progress} activeField={activeComponent?.field ?? null} />
            </div>
          </section>
        ) : null}
      </main>
    </>
  )
}

export default App
