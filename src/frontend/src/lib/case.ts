// Case-file metadata and formatting helpers shared by the intake workspace,
// the thought-process trace, and the results dashboard.
import type { CaseFields, UiComponent } from '../types'

export const MIN_DELIVERY_DATE = '1900-01-01'

// Fallback prompt when intake completes before terms have arrived.
export const TERMS_FALLBACK: UiComponent = {
  type: 'file_upload',
  field: 'terms_source',
  prompt: "Paste the seller's terms and conditions — or continue without them.",
}

export const NO_TERMS_ANSWER =
  "I don't have access to the seller's terms and conditions and can't get them — please continue without checking them."

export const fieldConfig: Array<{
  key: keyof CaseFields
  label: string
  empty: string
  format?: (value: NonNullable<CaseFields[keyof CaseFields]>) => string
}> = [
  {
    key: 'is_individual',
    label: 'Buyer',
    empty: 'Confirm buyer type',
    format: (value) => (value === true ? 'Individual consumer' : 'Not in consumer scope'),
  },
  { key: 'seller_name', label: 'Seller', empty: 'Not identified yet' },
  { key: 'product', label: 'Goods', empty: 'Product not confirmed' },
  { key: 'purchase_or_delivery_date', label: 'Timing', empty: 'Delivery date needed' },
  { key: 'grievance', label: 'Problem', empty: 'Fault not described' },
  {
    key: 'has_proof_of_purchase',
    label: 'Proof',
    empty: 'Statement or confirmation works',
    format: (value) => (value === true ? 'Available' : 'None yet — statement works'),
  },
  { key: 'desired_outcome', label: 'Outcome', empty: 'Refund, repair, replacement, or discount' },
  {
    key: 'terms_source',
    label: 'Terms',
    empty: 'Paste terms or continue without them',
    format: (value) => (value === 'none' ? 'None — statutory rights apply anyway' : String(value)),
  },
]

export function fieldHasValue(value: unknown) {
  return value !== undefined && value !== null && value !== ''
}

export function countKnownFields(fields: CaseFields | undefined) {
  if (!fields) return 0
  return fieldConfig.filter((item) => fieldHasValue(fields[item.key])).length
}

export function formatFieldValue(
  item: (typeof fieldConfig)[number],
  value: CaseFields[keyof CaseFields],
) {
  if (!fieldHasValue(value)) return item.empty
  if (item.format) return item.format(value as NonNullable<CaseFields[keyof CaseFields]>)
  if (typeof value === 'string') return value.replace(/_/g, ' ')
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

export function fieldTitle(field: string) {
  return fieldConfig.find((item) => item.key === field)?.label ?? field.replace(/_/g, ' ')
}

export function humaniseOption(option: string) {
  return option.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function labelRemedy(remedy: string) {
  return remedy.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function getTodayIso() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
