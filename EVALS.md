# FairClaimAI Eval Strategy

FairClaimAI is verified by three layers, ordered by how deterministic the
behavior under test is. Each layer covers what the layer below cannot.

| Layer | What it tests | Where | Trigger |
|---|---|---|---|
| L1 Deterministic tests | Contracts, legal boundary logic, ingestion, guardrails, orchestration | `tests/` (pytest) | every change |
| L2 Automated model evals | Live Gemini behavior: labels, remedies, drafts, injection, e2e flows | `evals/` (this repo) | pre-deploy gate |
| L3 External human validation | Whether L1+L2 encode the *right* answers, and whether the LLM judge can be trusted | ground-truth repo (separate checkout) + `evals/human_baseline.py` | milestone |

## 1. L1 — deterministic tests

Pytest covers everything that must not depend on a model: schema contracts,
`lookup_remedy_tier` day-boundary logic, T&C ingestion, injection pre-scan,
and orchestrator routing. Run with `uv run pytest`.

## 2. L2 — automated model eval suites

The eval runner exercises the real agents against curated scenarios:

```bash
uv run python -m evals.run --suites all --reps 1
```

It requires `GEMINI_API_KEY` in `.env`. Datasets live in `evals/datasets/`;
date-relative cases use runtime materialization so day-30/day-31 boundaries
stay meaningful over time.

### Suites

- `evals/suites/intake.py` — scripted personas through the intake agent;
  checks inferred values, missing slots, and generated UI components.
- `evals/suites/tc_analysis.py` — clause labels, statutory bases,
  prompt-injection propagation, explanation quality.
- `evals/suites/remedies.py` — remedy tier, primary remedy, statutory basis,
  and burden-of-proof framing against deterministic `lookup_remedy_tier`.
- `evals/suites/email_drafts.py` — drafts include the requested remedy,
  statutory basis, deadline language, escalation wording, disclaimer, and a
  rebuttal when T&C analysis found a problematic seller clause.
- `evals/suites/security.py` — hostile seller terms do not override agent
  instructions; deterministic injection flags survive into the final result.
- `evals/suites/e2e.py` — full personas through the real orchestrator with
  staged session state similar to the frontend.

### Gates vs judge scores

The runner treats gate failures (missing citation, wrong tier, dropped
injection flag, missing disclaimer) as real failures. LLM-judge rubric
scores are **advisory**: human calibration in L3 showed the judge saturates
at 5/5 where a solicitor scores 3–4 (leniency bias), so no pass/fail
decision rests on a judge score alone. Prose checks use tolerance bands, but
passing a band still requires the legal and safety constraints to hold.

Judge hygiene (`evals/judge.py`): the judge defaults to
`gemini-3.1-pro-preview`, separate from the fast/capable agent tiers
(override with `FAIRCLAIMAI_JUDGE_MODEL`); minimal rubric-bound prompts at
temperature 0; the judge sees only the rubric and the output, not agent
system prompts.

## 3. L3 — external human validation

Ground truth lives in a **separate repo** (checked out as a sibling of this
one) so labels cannot drift with the code: real UK retailer T&C documents
with stratified gold clause spans (regex-blacklist, paraphrased-blacklist,
grey-zone, compliant, plus synthetic hard cases including a prompt-injection
canary), remedy boundary cases, and an offline annotation UI. A UK-qualified
solicitor labels clause spans blind (label-then-reveal), reviews remedy
tier/burden, reviews whole outputs and email drafts, and independently
re-scores the payloads the LLM judge scored (judge calibration).

Because the solicitor's labels attach to *inputs* (clause spans, remedy
cases) rather than to a particular model output, they remain valid across
refactors. Score any checkout against them with:

```bash
uv run python -m evals.human_baseline --source frozen --annotations <export.json>  # reproduce the session
uv run python -m evals.human_baseline --source live   --annotations <export.json>  # score HEAD
```

`--source frozen` scores the pinned outputs the solicitor actually reviewed;
`--source live` re-runs the current tc_analysis and remedies agents on the
same inputs. Judge calibration and whole-output review are inherently pinned
to the reviewed outputs and are reported from the export as-is. The
ground-truth data is never copied into this repo and is not shared with
third parties.

Disagreements between the solicitor and L1's deterministic encoding are
surfaced, not silently overridden (e.g. burden of proof under the day-30
short-term right to reject, CRA 2015 s.19(14)).

## 4. Telemetry

Eval-only telemetry lives in `src/fairclaim/backend/telemetry.py` and is wired from
`evals/harness.py`. It records model calls, estimated cost, and guardrail
events for eval reports. Pricing can be overridden with
`FAIRCLAIMAI_PRICING_JSON`.

## 5. Outputs

Reports are written to `evals/results/` as Markdown files (suite runs as
`eval-<stamp>.md`, human-baseline scoring as `human_baseline-*.md`). They
are historical run artifacts; do not edit old reports to match new behavior.
