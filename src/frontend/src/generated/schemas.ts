// GENERATED FILE -- DO NOT EDIT.
// Source of truth: fairclaim.backend.schemas. Regenerate with:
//   uv run python -m fairclaim.backend.scripts.gen_frontend_types

export interface UiComponent {
  type: 'choice_card' | 'date_picker' | 'text_input' | 'file_upload' | 'confirm_card'
  field: string
  prompt: string
  options?: string[] | null
  accept?: string[] | null
  inferred_value?: string | null
}

export interface CaseFields {
  is_individual?: boolean | null
  seller_name?: string | null
  product?: string | null
  purchase_or_delivery_date?: string | null
  terms_source?: 'pasted' | 'none' | null
  grievance?: string | null
  desired_outcome?: 'refund' | 'repair' | 'replacement' | 'price_reduction' | null
  has_repair_or_replacement_been_attempted?: boolean | null
  has_proof_of_purchase?: boolean | null
}

export interface IntakeTurn {
  is_complete: boolean
  scope_gate_failure?: string | null
  next_component?: UiComponent | null
  collected_fields: CaseFields
}

export interface ClauseVerdict {
  clause_text: string
  label: 'BLACKLISTED' | 'POTENTIALLY_UNFAIR' | 'COMPLIANT'
  statutory_basis: string[]
  simple_explanation: string
  legal_explanation: string
  confidence: 'high' | 'medium' | 'low'
}

export interface TcAnalysisResult {
  clauses: ClauseVerdict[]
  overall_confidence: 'high' | 'moderate' | 'low'
  injection_flagged: boolean
  disclaimer: string
}

export interface RemedyResult {
  applicable_tier: 'TIER_0' | 'TIER_1' | 'TIER_2'
  primary_remedy: 'full_refund' | 'repair' | 'replacement' | 'price_reduction' | 'final_reject_refund'
  statutory_basis: string[]
  simple_explanation: string
  legal_explanation: string
  burden_of_proof: 'trader' | 'consumer'
  claim_strength: 'strong' | 'moderate' | 'weak'
  practical_barriers: string[]
  alternatives: string[]
  disclaimer: string
}

export interface EmailDraft {
  remedy: 'full_refund' | 'repair' | 'replacement' | 'price_reduction' | 'final_reject_refund'
  subject: string
  polite_body: string
  firm_body: string
  formal_body: string
  response_deadline_days?: number
}

export interface SessionStateContract {
  intake_turn?: IntakeTurn | null
  tc_analysis_result?: TcAnalysisResult | null
  remedy_result?: RemedyResult | null
  email_drafts?: EmailDraft[] | null
}
