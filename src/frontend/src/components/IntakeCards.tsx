import { useState } from 'react'
import {
  Check,
  ChevronRight,
  Clipboard,
  RefreshCcw,
  Scale,
  ShieldCheck,
  X,
} from 'lucide-react'
import { ingestTerms } from '../api'
import {
  MIN_DELIVERY_DATE,
  NO_TERMS_ANSWER,
  fieldConfig,
  fieldHasValue,
  fieldTitle,
  formatFieldValue,
  getTodayIso,
  humaniseOption,
} from '../lib/case'
import type { CaseFields, UiComponent } from '../types'

type AnswerHandler = (answer: string, stateDelta?: Record<string, unknown>) => void

const BOOLEAN_CONFIRM_PROMPTS: Record<string, string> = {
  is_individual: 'Did you buy this mainly for personal use, rather than for trade, business or professional use?',
  has_repair_or_replacement_been_attempted: 'Has the seller already attempted a repair or replacement?',
  has_proof_of_purchase: 'Do you have any proof of purchase? A bank statement or order confirmation counts.',
}

function isBooleanConfirm(component: UiComponent) {
  return component.type === 'confirm_card' && component.field in BOOLEAN_CONFIRM_PROMPTS
}

export function GeneratedCard({
  component,
  busy,
  onAnswer,
}: {
  component: UiComponent
  busy: boolean
  onAnswer: AnswerHandler
}) {
  if (component.field === 'terms_source') {
    return <TermsIngestionCard component={component} busy={busy} onAnswer={onAnswer} />
  }

  if (component.type === 'choice_card') {
    return (
      <article className="question-card">
        <CardLabel component={component} />
        <h2>{component.prompt}</h2>
        <div className="choice-grid">
          {(component.options ?? []).map((option) => (
            <button key={option} type="button" onClick={() => onAnswer(option)} disabled={busy}>
              <span>{humaniseOption(option)}</span>
              <ChevronRight size={17} />
            </button>
          ))}
        </div>
      </article>
    )
  }

  if (component.type === 'confirm_card') {
    if (isBooleanConfirm(component)) {
      return <BooleanConfirmCard component={component} busy={busy} onAnswer={onAnswer} />
    }
    return <ConfirmGeneratedCard component={component} busy={busy} onAnswer={onAnswer} />
  }

  if (component.type === 'date_picker') {
    return <DateGeneratedCard component={component} busy={busy} onAnswer={onAnswer} />
  }

  return <TextGeneratedCard component={component} busy={busy} onAnswer={onAnswer} />
}

function CardLabel({ component }: { component: UiComponent }) {
  return (
    <div className="card-label">
      <span>{fieldTitle(component.field)}</span>
      <small>{component.type.replace('_', ' ')}</small>
    </div>
  )
}

function BooleanConfirmCard({
  component,
  busy,
  onAnswer,
}: {
  component: UiComponent
  busy: boolean
  onAnswer: (answer: string) => void
}) {
  return (
    <article className="question-card">
      <CardLabel component={component} />
      <h2>{BOOLEAN_CONFIRM_PROMPTS[component.field]}</h2>
      <div className="choice-grid">
        <button type="button" onClick={() => onAnswer('Yes')} disabled={busy}>
          <span>Yes</span>
          <Check size={17} />
        </button>
        <button type="button" onClick={() => onAnswer('No')} disabled={busy}>
          <span>No</span>
          <X size={17} />
        </button>
      </div>
    </article>
  )
}

function ConfirmGeneratedCard({
  component,
  busy,
  onAnswer,
}: {
  component: UiComponent
  busy: boolean
  onAnswer: (answer: string) => void
}) {
  const [isCorrecting, setIsCorrecting] = useState(false)
  const [correction, setCorrection] = useState(component.inferred_value ?? '')

  return (
    <article className="question-card">
      <CardLabel component={component} />
      <h2>{component.prompt}</h2>
      <div className="inference-box">
        <span>Inferred from your story</span>
        <strong>{component.inferred_value}</strong>
      </div>
      <div className="card-actions">
        <button
          type="button"
          className="primary-action"
          onClick={() => onAnswer(component.inferred_value ?? 'Yes, that is correct.')}
          disabled={busy}
        >
          <Check size={18} /> Yes, use this
        </button>
        <button
          type="button"
          className="secondary-action"
          onClick={() => setIsCorrecting((value) => !value)}
          disabled={busy}
        >
          Correct it
        </button>
      </div>
      {isCorrecting && (
        <div className="correction-row">
          <input
            type="text"
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
            aria-label="Corrected value"
          />
          <button
            type="button"
            className="primary-action"
            onClick={() => onAnswer(correction)}
            disabled={!correction.trim() || busy}
          >
            Save correction
          </button>
        </div>
      )}
    </article>
  )
}

function DateGeneratedCard({
  component,
  busy,
  onAnswer,
}: {
  component: UiComponent
  busy: boolean
  onAnswer: (answer: string) => void
}) {
  const [value, setValue] = useState(component.inferred_value ?? '')
  const maxDate = getTodayIso()

  return (
    <article className="question-card">
      <CardLabel component={component} />
      <h2>{component.prompt}</h2>
      <div className="date-row">
        <input
          type="date"
          min={MIN_DELIVERY_DATE}
          max={maxDate}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label="Delivery date"
        />
        <button type="button" className="primary-action" onClick={() => onAnswer(value)} disabled={!value || busy}>
          Continue
        </button>
      </div>
    </article>
  )
}

function TextGeneratedCard({
  component,
  busy,
  onAnswer,
}: {
  component: UiComponent
  busy: boolean
  onAnswer: (answer: string) => void
}) {
  const [value, setValue] = useState('')
  return (
    <article className="question-card">
      <CardLabel component={component} />
      <h2>{component.prompt}</h2>
      <textarea value={value} onChange={(event) => setValue(event.target.value)} rows={4} aria-label="Your answer" />
      <div className="card-actions">
        <button type="button" className="primary-action" onClick={() => onAnswer(value)} disabled={!value.trim() || busy}>
          Continue
        </button>
      </div>
    </article>
  )
}

function TermsIngestionCard({
  component,
  busy,
  onAnswer,
}: {
  component: UiComponent
  busy: boolean
  onAnswer: AnswerHandler
}) {
  const [text, setText] = useState('')
  const [localBusy, setLocalBusy] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  async function submit() {
    setLocalError(null)

    setLocalBusy(true)
    try {
      const clean = await ingestTerms('pasted', text)
      onAnswer('Terms and conditions received via pasted text.', { terms_clean: clean })
    } catch (e) {
      setLocalError(String(e instanceof Error ? e.message : e))
    } finally {
      setLocalBusy(false)
    }
  }

  return (
    <article className="question-card terms-card">
      <CardLabel component={component} />
      <h2>{component.prompt}</h2>
      <textarea value={text} onChange={(event) => setText(event.target.value)} rows={5} aria-label="Pasted terms" />
      <div className="ingestion-note">
        <ShieldCheck size={17} />
        <p>Pasted terms are size-limited and wrapped as untrusted evidence before analysis.</p>
      </div>
      {localError && <p className="inline-error">{localError}</p>}
      <div className="card-actions">
        <button
          type="button"
          className="primary-action"
          onClick={submit}
          disabled={busy || localBusy || !text.trim()}
        >
          {localBusy ? 'Ingesting…' : 'Ingest terms and analyse'}
        </button>
        <button
          type="button"
          className="ghost-action"
          onClick={() => onAnswer(NO_TERMS_ANSWER, { terms_opted_out: true })}
          disabled={busy || localBusy}
          title="Your statutory rights apply whatever the small print says — the analysis continues without the terms check."
        >
          I don't have the terms — continue anyway
        </button>
      </div>
    </article>
  )
}

export function ScopeGateCard({ message, onReset }: { message: string; onReset: () => void }) {
  return (
    <div className="scope-gate-card">
      <div className="scope-gate-icon" aria-hidden="true">
        <Scale size={22} />
      </div>
      <h2>This one is outside what the tool can advise on.</h2>
      <p>{message}</p>
      <button type="button" className="secondary-action" onClick={onReset}>
        <RefreshCcw size={17} /> Start a different case
      </button>
    </div>
  )
}

export function CaseFile({
  fields,
  progress,
  activeField,
}: {
  fields: CaseFields
  progress: number
  activeField: string | null
}) {
  return (
    <aside className="case-file" aria-label="Case file">
      <header>
        <div>
          <Clipboard size={16} />
          <h2>Case file</h2>
        </div>
        <small>{progress}%</small>
      </header>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Case completeness"
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <ul className="fact-list">
        {fieldConfig.map((item) => {
          const value = fields[item.key]
          const isActive = activeField === item.key
          const hasValue = fieldHasValue(value)
          return (
            <li className={`fact-row ${isActive ? 'active' : ''}`} key={item.key}>
              <div>
                <span>{item.label}</span>
                <strong>{hasValue ? formatFieldValue(item, value) : item.empty}</strong>
              </div>
              <small className={isActive ? 'asking' : hasValue ? 'captured' : 'needed'}>
                {isActive ? 'Asking' : hasValue ? 'Captured' : 'Needed'}
              </small>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
