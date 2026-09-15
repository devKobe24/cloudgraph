# Changelog

## 0.1.0 — unreleased

First release.

- `awsgraph` CLI: `init`, `design`, `validate`, `build`, `estimate`, `stats`,
  `query`, `path`, `explain`, `affected`, `export`.
- Seven resource types (VPC, Subnet, EC2, EBS, RDS, ALB, NAT Gateway) in
  `ap-northeast-2`, priced from a local versioned catalog.
- `nx.MultiDiGraph` model that preserves direction and parallel relations.
- Standalone `graph.html` viewer and `AWS_REPORT.md`.
- React Flow designer shipped prebuilt in the wheel; no Node required to use it.
- Python and TypeScript estimators pinned together by a shared parity fixture.

Not included: AWS account scanning, real Price List API calls, Multi-AZ,
Savings Plans, multi-region, IAM analysis. See `docs/PRICING.md`.
