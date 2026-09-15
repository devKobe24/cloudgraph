# Review — ec2-rds

## What worked
- `awsgraph path "App Server" "App Database"` prints the one-hop `connects-to`
  edge, which is the question this example exists to answer.
- `awsgraph affected "App Database"` correctly names the App Server: the policy
  walks `connects-to` backwards rather than doing a plain reverse BFS.

## Simplifications in the pricing
- RDS is Single-AZ only. A Multi-AZ deployment roughly doubles the compute line
  and v0.1 rejects the flag outright rather than pricing it wrong.
- Backup storage beyond the provisioned 20 GiB is not modelled.
- Both subnets are in different AZs but cross-AZ data transfer is not priced.

## Graph layout
- No positions in the design file, so both the viewer and the designer place the
  nodes by containment depth. Readable, but the DB subnet edge crosses the app
  subnet edge.

## Next version
- Multi-AZ, and a warning when a database subnet has only one AZ.
