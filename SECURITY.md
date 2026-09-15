# Security

## What v0.1 does and does not do

```
NO AWS CREDENTIAL REQUIRED
NO NETWORK CALL DURING BUILD
NO TELEMETRY
NO REMOTE DATABASE
NO SECRET COLLECTION
NO RESOURCE MUTATION
LOCAL FILES ONLY
```

`awsgraph build` works with the network unplugged, and a test enforces that by
blocking sockets while it runs.

## Untrusted input

A design file is untrusted. Resource names reach both generated HTML files.

- JSON embedded in HTML has `<`, `>` and `&` escaped so a name cannot terminate
  the `<script>` block it sits in.
- The viewer writes every user string with `textContent`; it never uses
  `innerHTML`.
- Unknown keys in a design file are rejected rather than ignored.
- Input sizes are capped: 16 MiB for a design file, 512 MiB for `graph.json`.

## Writes

Artifacts are rendered fully in memory, then written through a temporary file and
`os.replace`. A failure mid-build leaves the previous output intact. Output goes
to `awsgraph-out/` unless `--out` says otherwise.

## When v0.2 adds scanning

- read-only IAM permissions only
- the standard AWS credential chain, no bespoke credential handling
- never collect secret values: access key secrets, Secrets Manager values,
  SSM SecureString values, RDS passwords, or raw user data
- never write credentials into `graph.json`

## Reporting

Open a GitHub issue for anything that is not itself sensitive. For a
vulnerability, use GitHub's private security advisory form on this repository.
