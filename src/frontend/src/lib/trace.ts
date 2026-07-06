// The plain-language agent trace shown in the "Thought process" collapsible.
// 'user' = something the user said, 'agent' = a question or verdict from the
// agent, 'step' = work the agent did along the way.
export type TraceKind = 'user' | 'agent' | 'step'

export interface TraceEntry {
  kind: TraceKind
  label: string
  detail?: string
}
