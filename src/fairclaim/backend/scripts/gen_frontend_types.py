"""Generates src/frontend/src/generated/schemas.ts from fairclaim.backend.schemas.

fairclaim.backend.schemas is the single source of truth for the frontend/backend
wire contract (session-state shape + the UI component catalog). Frontend
code used to hand-mirror these as TS interfaces — a silent-drift risk called
out in its own comments. Generating them instead means a backend schema
change either propagates automatically or fails the frontend TS build
loudly, never silently.

Run after changing fairclaim.backend.schemas:

    uv run python -m fairclaim.backend.scripts.gen_frontend_types

Deliberately dependency-free (no `json-schema-to-typescript`, no Node step):
walks Pydantic v2's resolved `model_fields` directly rather than round-
tripping through JSON Schema, since this project's models are flat enough
(Literal / str / bool / int / list / Optional / nested BaseModel — no
generics or $refs) that direct introspection is simpler than resolving
JSON Schema $defs.
"""

from __future__ import annotations

import types
import typing
from pathlib import Path

from pydantic import BaseModel

from fairclaim.backend.schemas import (
    CaseFields,
    ClauseVerdict,
    EmailDraft,
    IntakeTurn,
    RemedyResult,
    SessionStateContract,
    TcAnalysisResult,
    UiComponent,
)

# Order matters for readability only (TS doesn't require declare-before-use)
# -- put leaf models first, the top-level contract last.
MODELS: list[type[BaseModel]] = [
    UiComponent,
    CaseFields,
    IntakeTurn,
    ClauseVerdict,
    TcAnalysisResult,
    RemedyResult,
    EmailDraft,
    SessionStateContract,
]

OUT_PATH = Path(__file__).resolve().parents[3] / "frontend" / "src" / "generated" / "schemas.ts"

_PRIMITIVES: dict[type, str] = {str: "string", bool: "boolean", int: "number", float: "number"}


def _ts_type(annotation: object) -> str:
    origin = typing.get_origin(annotation)

    if origin is typing.Literal:
        return " | ".join(repr(a) for a in typing.get_args(annotation))

    if origin in (types.UnionType, typing.Union):
        args = typing.get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        rendered = " | ".join(_ts_type(a) for a in non_none)
        if len(non_none) != len(args):
            rendered += " | null"
        return rendered

    if origin is list:
        (inner,) = typing.get_args(annotation)
        return f"{_ts_type(inner)}[]"

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    if annotation in _PRIMITIVES:
        return _PRIMITIVES[annotation]

    raise TypeError(f"gen_frontend_types: no TS mapping for annotation {annotation!r}")


def _render_model(model: type[BaseModel]) -> str:
    lines = [f"export interface {model.__name__} {{"]
    for name, field in model.model_fields.items():
        optional = "" if field.is_required() else "?"
        lines.append(f"  {name}{optional}: {_ts_type(field.annotation)}")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    header = (
        "// GENERATED FILE -- DO NOT EDIT.\n"
        "// Source of truth: fairclaim.backend.schemas. Regenerate with:\n"
        "//   uv run python -m fairclaim.backend.scripts.gen_frontend_types\n\n"
    )
    body = "\n\n".join(_render_model(model) for model in MODELS)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(header + body + "\n")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
