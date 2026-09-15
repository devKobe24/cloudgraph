# Contributing

```bash
uv sync --frozen
uv run --frozen pytest
uv run --frozen ruff check awsgraph tools tests
pre-commit install
```

## The one rule that matters

`awsgraph/schema.py` is the single source of truth for the file format.

Touch it and you must regenerate:

```bash
uv run --frozen python -m tools.codegen     # web resource spec + JSON Schema
uv run --frozen python -m tools.build_web   # designer bundle (needs Node)
```

CI runs both with `--check` and fails if the committed files are stale. This
exists because the designer used to carry a hand-written copy of the schema, and
nothing caught it when the two disagreed.

## Adding a resource type

Seven steps. Fewer than seven means the resource is half-supported.

1. Model it in `awsgraph/schema.py`
2. Add its pairs to `CONNECTION_RULES` in `awsgraph/validate.py`
3. Write a calculator in `awsgraph/pricing.py` and register it in `CALCULATORS`
4. Add rates to `awsgraph/data/pricing/ap-northeast-2.json`
5. Add a seed value to `SEEDS` in `tools/codegen.py` for every required field
   (codegen fails loudly if you forget)
6. Add a case to `tests/fixtures/pricing_cases.json` — it binds the Python and
   TypeScript estimators together
7. Regenerate, and run both test suites

## Changing anything that prices

`tests/fixtures/pricing_cases.json` is a contract between two languages. Run
`uv run --frozen pytest` **and** `npm --prefix webui test`. A change that passes
one and not the other means the designer would show a number the CLI disagrees
with.

## Worked examples

`worked/*/review.md` records what the tool got wrong or simplified. Keep it
honest — it is a quality note, not a showcase. If a pipeline change alters the
committed output, `tests/test_worked.py` will say so; confirm the change is
intended before regenerating.
