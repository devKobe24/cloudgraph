# AWSGraph

Local-first AWS architecture graph and cost estimator. Draw or write an
architecture, get a monthly estimate, then query the same graph from the CLI.

No AWS credentials. No network calls during a build. No database.

```bash
uv tool install awsgraph

awsgraph init architecture.awsgraph.json
awsgraph design architecture.awsgraph.json     # visual editor in your browser
awsgraph build architecture.awsgraph.json      # graph.json + graph.html + AWS_REPORT.md

awsgraph estimate
awsgraph explain "Backend EC2"
awsgraph path "Public ALB" "Main RDS"
awsgraph affected "Main RDS"
```

## What it covers

VPC, Subnet, EC2, EBS, RDS, ALB and NAT Gateway in `ap-northeast-2`, priced from
a local versioned catalog.

**The estimate is not a bill.** Rates are maintainer-entered list prices, usage
is whatever you typed, and public IPv4, data transfer, snapshots, taxes, credits,
Savings Plans and the free tier are not modelled. A resource whose rate is
missing is reported as `unpriced`, never as zero. See
[docs/PRICING.md](docs/PRICING.md).

## Output

```
awsgraph-out/
├── graph.json        derived artifact; every query command reads this
├── graph.html        standalone viewer, opens from the filesystem
└── AWS_REPORT.md     what a person reads
```

Your `.awsgraph.json` is the editable source and is never written to by a build.

## Worked examples

`worked/` holds three real runs with their output committed, each with a
`review.md` recording what the tool got wrong or simplified. They are quality
notes, not a showcase.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — pipeline and module layout
- [docs/FILE_FORMAT.md](docs/FILE_FORMAT.md) — the two file formats
- [docs/PRICING.md](docs/PRICING.md) — where the numbers come from

## Development

```bash
uv sync --frozen
uv run --frozen pytest
```

The designer is a React Flow app in `webui/`, built into the wheel as a single
HTML file. **Contributors need Node for that; users never do.**

```bash
npm --prefix webui ci
npm --prefix webui test          # pricing parity against the Python estimator
uv run --frozen python -m tools.build_web
uv run --frozen python -m tools.codegen
```

`awsgraph/schema.py` is the single source of truth for the file format. The
designer's field definitions and connection rules are generated from it; CI runs
`python -m tools.codegen --check` and fails if the committed copy is stale.

## What CI enforces

| Job | Blocking |
|---|---|
| generated assets match `schema.py` | yes |
| pytest on Python 3.10 / 3.12 / 3.13 / 3.14 | yes |
| wheel installs and runs in a clean env | yes |
| webui tests and build | yes |
| ruff | yes |
| bandit, pip-audit | **no — advisory** |

The security job is `continue-on-error` because upstream advisories land
unrelated to the change under review. Read its output; green there does not mean
clean.

## License

MIT
