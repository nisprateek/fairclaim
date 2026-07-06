# FairClaimAI Frontend

Vite + React + TypeScript frontend for FairClaimAI.

The production flow talks to the ADK REST API exposed by `backend/main.py`. It renders the small-print verdicts and the remedy ladder separately, but the generated complaint letter also receives the T&C verdicts so firm/formal tones can rebut the seller's actual problematic clauses.

## Commands

```bash
npm install
npm run dev
npm run build
npm run gen:types
```

## Branding

- Logo asset: `public/fairclaimai-logo.jpeg`
- Primary navy: `#022a5f`
- Accent violet: `#9988ff`
- Shared CSS tokens: `src/index.css`

Keep the first screen as the usable prompt surface, not a marketing landing page.
