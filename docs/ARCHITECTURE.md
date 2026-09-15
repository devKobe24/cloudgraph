# Architecture

## The shape of the thing

Python is the product. The browser is an interface onto it.

```
.awsgraph.json ──┐
                 ├─> load ─> validate ─> build ─> estimate ─> analyze ─> report/export
designer ────────┘                         │
                                           v
                                   nx.MultiDiGraph
                                           │
                        awsgraph-out/{graph.json, graph.html, AWS_REPORT.md}
                                           │
                     query · path · explain · affected · estimate · stats · export
```

If the browser assets break, `build`, `estimate`, `query`, `path`, `explain` and
`affected` all still work. That is deliberate, and there is a test for it.

## Pipeline contracts

Each stage has one job and is reachable as a plain function.

| Stage | In | Out | Does not |
|---|---|---|---|
| `load` | file path | `Architecture` | build a graph |
| `validate_design` | model | list of problems | compute cost |
| `build` | model | `MultiDiGraph` | look up prices |
| `estimate` | graph + catalog | cost on the graph | change topology |
| `analyze` | costed graph | analysis dict | write files |
| `report.generate` | graph + analysis | Markdown | touch the network |
| `export` | graph | files | modify the source model |

## Module dependency direction

```
cli · design · export
        v
load · validate · build · estimate · analyze · query · affected
        v
schema · paths · pricing
```

`schema.py` is the single source of truth for the file format. `tools/codegen.py`
generates the web assets from it and CI fails if they drift.

## Decisions worth knowing

**`MultiDiGraph`, not `DiGraph`.** Two resources can be joined by more than one
relation and a plain digraph silently collapses them.

**Money is `Decimal`, stored as strings.** Float rounding differs between Python
and JavaScript; a half-cent case in the parity fixture pins this down.

**A missing rate is `unpriced`, never `0`.** See `docs/PRICING.md`.

**Source and artifact are separate files.** See `docs/FILE_FORMAT.md`.

**Writes are atomic.** Every artifact renders fully in memory before anything
touches disk, then lands via `os.replace`, so a failure leaves the previous
build intact.

**Two viewers, on purpose.** `graph.html` is 13 KB of dependency-free JS because
it is generated on every build and shared as a file. The designer is a 438 KB
React Flow bundle because authoring needs drag handles and edge creation. They
read different data — the designer edits the source file, the viewer reads the
built artifact — so sharing a canvas would buy less than it costs.

## v0.2 seams

- Node `provenance` is `{"kind": "declared"}` today; a scanner writes
  `{"kind": "discovered", "arn": ...}`.
- `build()` takes a normalized model, so `discover → collect → normalize` can be
  placed in front of it without touching anything downstream.
- `boto3` belongs in an optional extra, never a base dependency.
