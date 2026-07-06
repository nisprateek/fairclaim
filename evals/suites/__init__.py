"""Suite registry — evals/run.py dispatches through SUITES."""

from evals.suites import e2e, email_drafts, intake, remedies, security, tc_analysis

# Cheap/staged suites first; multi-turn conversational suites last.
SUITES = {
    "tc": tc_analysis.run,
    "security": security.run,
    "remedies": remedies.run,
    "email": email_drafts.run,
    "intake": intake.run,
    "e2e": e2e.run,
}
