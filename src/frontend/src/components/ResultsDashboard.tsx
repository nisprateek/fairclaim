import { useState } from 'react'
import type { CSSProperties } from 'react'
import {
  AlertTriangle,
  Check,
  Clock3,
  Copy,
  Info,
  Mail,
  Scale,
  Search,
  ShieldCheck,
} from 'lucide-react'
import { labelRemedy } from '../lib/case'
import type { TraceEntry } from '../lib/trace'
import type { EmailDraft, ResultBundle } from '../types'
import { ThoughtProcess } from './ThoughtProcess'

// The sternness levels, politest first — each email draft carries one body
// per level (see EmailDraft in the generated schema).
const TONES = [
  {
    key: 'polite_body',
    label: 'Polite',
    hint: 'A friendly first ask — most disputes settle here.',
  },
  {
    key: 'firm_body',
    label: 'Firm',
    hint: 'Cites your legal rights and sets a 14-day deadline.',
  },
  {
    key: 'formal_body',
    label: 'Formal',
    hint: 'A final notice spelling out the escalation steps.',
  },
] as const

function emailBody(email: EmailDraft, tone: number) {
  return email[TONES[tone].key]
}

function reveal(index: number): CSSProperties {
  return { '--reveal-index': index } as CSSProperties
}

// The plain-English text is always visible; the statutory reasoning sits
// behind a native disclosure element — no state to manage.
function LegalDetail({ text }: { text: string }) {
  return (
    <details className="legal-detail">
      <summary>Show legal detail</summary>
      <p>{text}</p>
    </details>
  )
}

function RemedyStep({
  title,
  basis,
  copy,
  active = false,
}: {
  title: string
  basis: string
  copy: string
  active?: boolean
}) {
  return (
    <article className={`remedy-step ${active ? 'active' : ''}`}>
      <span className="remedy-dot" />
      <div>
        <strong>{title}</strong>
        <p>{copy}</p>
        <small>{basis}</small>
      </div>
    </article>
  )
}

export function ResultsDashboard({
  results,
  trace,
}: {
  results: ResultBundle
  trace: TraceEntry[]
}) {
  const [selectedEmail, setSelectedEmail] = useState(0)
  const [tone, setTone] = useState(0)
  const [copied, setCopied] = useState(false)
  const email = results.emails[selectedEmail]

  return (
    <section className="results">
      <div className="reveal" style={reveal(0)}>
        <ThoughtProcess trace={trace} />
      </div>

      <section className="outcome-hero reveal" style={reveal(1)}>
        <span className="hero-blob hero-blob-a" aria-hidden="true" />
        <span className="hero-blob hero-blob-b" aria-hidden="true" />
        <div className="outcome-body">
          <span className="hero-eyebrow">Best-supported remedy</span>
          <h1>{labelRemedy(results.remedy.primary_remedy)}</h1>
          <p>{results.remedy.simple_explanation}</p>
          <div className="hero-chips">
            {results.remedy.statutory_basis.map((basis) => (
              <span key={basis}>{basis}</span>
            ))}
          </div>
        </div>
      </section>

      <div className="results-grid">
        <section className="result-card reveal" style={reveal(2)}>
          <header className="result-card-head">
            <div>
              <Search size={17} />
              <h2>Small print check</h2>
            </div>
            <small>{results.tc.overall_confidence} confidence</small>
          </header>

          {results.tc.injection_flagged && (
            <div className="warning-line">
              <AlertTriangle size={17} />
              <p>Possible prompt-injection text was detected in the submitted terms.</p>
            </div>
          )}

          {!results.termsProvided && (
            <div className="no-terms-note">
              <ShieldCheck size={18} />
              <p>
                No terms were provided, and that's fine: your statutory rights under the Consumer
                Rights Act 2015 apply <strong>regardless of any small print</strong> — a trader
                cannot contract out of them (s.31). The remedy and letter rest entirely on the Act.
              </p>
            </div>
          )}

          <div className="clause-list">
            {results.tc.clauses.map((clause) => (
              <article className="clause" key={clause.clause_text}>
                <div className="clause-labels">
                  <span className={`verdict ${clause.label.toLowerCase()}`}>
                    {clause.label.replace('_', ' ').toLowerCase()}
                  </span>
                  {clause.statutory_basis.map((basis) => (
                    <span className="basis" key={basis}>
                      {basis}
                    </span>
                  ))}
                  <span className="confidence">{clause.confidence}</span>
                </div>
                <blockquote>{clause.clause_text}</blockquote>
                <p>{clause.simple_explanation}</p>
                <LegalDetail text={clause.legal_explanation} />
              </article>
            ))}
          </div>
        </section>

        <section className="result-card reveal" style={reveal(3)}>
          <header className="result-card-head">
            <div>
              <Scale size={17} />
              <h2>Remedy ladder</h2>
            </div>
            <div className="remedy-head-tags">
              <span className={`claim-strength ${results.remedy.claim_strength}`}>
                {results.remedy.claim_strength} claim
              </span>
              <small>{results.remedy.applicable_tier.replace('TIER_', 'tier ')}</small>
            </div>
          </header>

          <div className="burden-card">
            <Clock3 size={18} />
            <div>
              <strong>Burden of proof: {results.remedy.burden_of_proof}</strong>
              <p>{results.remedy.simple_explanation}</p>
              <LegalDetail text={results.remedy.legal_explanation} />
            </div>
          </div>

          {results.remedy.practical_barriers.length > 0 && (
            <div className="barriers-card">
              <div className="barriers-head">
                <AlertTriangle size={17} />
                <strong>What you'll need to make this stick</strong>
              </div>
              <ul>
                {results.remedy.practical_barriers.map((barrier) => (
                  <li key={barrier}>{barrier}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="remedy-path">
            <RemedyStep
              active={results.remedy.applicable_tier === 'TIER_0'}
              title="Short-term right to reject"
              basis="s.20, s.22"
              copy="Full refund within 30 days of receiving the goods — repair or replacement (s.23) is also open in this window."
            />
            <RemedyStep
              active={results.remedy.applicable_tier === 'TIER_1'}
              title="Repair or replacement"
              basis="s.23"
              copy="Free, within a reasonable time, without significant inconvenience — the consumer chooses which."
            />
            <RemedyStep
              active={results.remedy.applicable_tier === 'TIER_2'}
              title="Price reduction or final reject"
              basis="s.24"
              copy="Unlocked after one failed repair or replacement attempt."
            />
          </div>
        </section>
      </div>

      <section className="letter-card reveal" style={reveal(4)}>
        <header className="result-card-head">
          <div>
            <Mail size={17} />
            <h2>Your complaint letter</h2>
          </div>
          <button
            type="button"
            className="primary-action copy-action"
            onClick={() => {
              void navigator.clipboard.writeText(`Subject: ${email.subject}\n\n${emailBody(email, tone)}`)
              setCopied(true)
              window.setTimeout(() => setCopied(false), 1600)
            }}
          >
            {copied ? <Check size={17} /> : <Copy size={17} />} {copied ? 'Copied' : 'Copy letter'}
          </button>
        </header>

        <div className="letter-controls">
          {results.emails.length > 1 && (
            <div className="email-tabs" role="tablist" aria-label="Letter variant">
              {results.emails.map((draft, index) => (
                <button
                  type="button"
                  className={index === selectedEmail ? 'selected' : ''}
                  onClick={() => setSelectedEmail(index)}
                  key={`${draft.remedy}-${index}`}
                >
                  {labelRemedy(draft.remedy)}
                </button>
              ))}
            </div>
          )}
          <div className="tone-control">
            <div className="tone-segments" role="tablist" aria-label="Letter tone">
              {TONES.map((item, index) => (
                <button
                  type="button"
                  key={item.key}
                  className={index === tone ? 'selected' : ''}
                  onClick={() => setTone(index)}
                >
                  {index === tone && <Check size={14} />}
                  {item.label}
                </button>
              ))}
            </div>
            <p className="tone-hint">{TONES[tone].hint}</p>
          </div>
        </div>

        <article className="letter-doc">
          <header>
            <span>Subject</span>
            <strong>{email.subject}</strong>
            {tone > 0 && <small>{email.response_deadline_days ?? 14}-day response deadline</small>}
          </header>
          <pre>{emailBody(email, tone)}</pre>
        </article>

        {/* For the user, not the seller — deliberately outside the letter
            document so it is never copied along with the letter. */}
        <p className="letter-note">
          <Info size={16} />
          <span>{results.remedy.disclaimer}</span>
        </p>
      </section>
    </section>
  )
}
