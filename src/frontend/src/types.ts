// Re-exports the backend/schemas.py contract (see ./generated/schemas.ts —
// regenerate with `uv run python -m backend.scripts.gen_frontend_types`
// after changing backend/schemas.py). Add frontend-only types below this line.
import type { EmailDraft, RemedyResult, TcAnalysisResult } from './generated/schemas'

export type {
  UiComponent,
  CaseFields,
  IntakeTurn,
  ClauseVerdict,
  TcAnalysisResult,
  RemedyResult,
  EmailDraft,
  SessionStateContract,
} from './generated/schemas'

export interface ResultBundle {
  tc: TcAnalysisResult
  remedy: RemedyResult
  emails: EmailDraft[]
  termsProvided: boolean
}
