# Review — three-tier

The example that exercises every v0.1 resource type and every connection rule.

## What worked
- All seven resource types price without a gap: $287.54, no unpriced resources.
- The NAT gateway sits in the public subnet (`contains`) while the app subnet
  egresses through it (`routes-to`). Both edges survive into `graph.json`,
  which is the reason the graph is a MultiDiGraph.
- `awsgraph affected "Main RDS"` walks up two levels: EC2, then the ALB.

## Simplifications in the pricing
- 750 LCU-hours and 300 processed GB are guesses typed into the design file.
  These two numbers move the total more than anything else here and nothing
  validates them against reality.
- ALB fixed hours round to a half cent (0.0225 x 730 = 16.425 -> 16.43). Worth
  knowing when comparing against a bill line by line.
- No public IPv4 charge, which a real internet-facing ALB and NAT both incur.

## Graph layout
- Auto-placed. The `contains` edge from the DB subnet to RDS sweeps across the
  middle of the canvas. Opening it in `awsgraph design` and dragging two nodes
  fixes it, and the positions then persist.

## Next version
- Price public IPv4 addresses. It is a small per-hour number on every example
  here and its absence makes every total slightly optimistic.
