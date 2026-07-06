// Empty in production: the built frontend is served by the same FastAPI
// process as the API (see backend/main.py's static mount), so relative URLs
// already hit the right origin. Local dev (`npm run dev` on :5173, backend
// on :8000) needs an absolute URL instead — set via frontend/.env.development.
const BACKEND_URL = import.meta.env.VITE_API_BASE_URL ?? ''
const APP_NAME = 'consumer_rights'

async function createSession(userId: string, sessionId: string) {
  const res = await fetch(`${BACKEND_URL}/apps/${APP_NAME}/users/${userId}/sessions/${sessionId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw new Error(`Failed to create session: HTTP ${res.status}`)
}

async function runTurn(
  userId: string,
  sessionId: string,
  message: string,
  stateDelta?: Record<string, unknown>,
) {
  const res = await fetch(`${BACKEND_URL}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      appName: APP_NAME,
      userId,
      sessionId,
      newMessage: { role: 'user', parts: [{ text: message }] },
      ...(stateDelta ? { stateDelta } : {}),
    }),
  })
  if (!res.ok) throw new Error(`Agent run failed: HTTP ${res.status}`)
}

async function getSessionState(userId: string, sessionId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${BACKEND_URL}/apps/${APP_NAME}/users/${userId}/sessions/${sessionId}`)
  if (!res.ok) throw new Error(`Failed to read session: HTTP ${res.status}`)
  const session = await res.json()
  return session.state ?? {}
}

/**
 * Create a session (if needed) and run one turn, returning the updated state.
 *
 * `stateDelta` sets session-state keys directly alongside the conversational
 * message — used only for `terms_clean` (the extracted T&C text), so the
 * orchestrator gets the full text without it ever being transcribed through
 * the model as a chat message. See backend/schemas.py's SessionStateContract
 * for the state keys the response may contain.
 */
export async function sendTurn(
  userId: string,
  sessionId: string,
  message: string,
  isFirstTurn: boolean,
  stateDelta?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  if (isFirstTurn) await createSession(userId, sessionId)
  await runTurn(userId, sessionId, message, stateDelta)
  return getSessionState(userId, sessionId)
}

export type IngestMethod = 'pasted'

/** Extract clean T&C text via the backend's security-hardened ingestion endpoint. */
export async function ingestTerms(
  method: IngestMethod,
  value: string,
): Promise<string> {
  const form = new FormData()
  form.set('method', method)
  form.set('text', value)

  const res = await fetch(`${BACKEND_URL}/ingest/terms`, { method: 'POST', body: form })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`)
  return data.text
}

export function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}
