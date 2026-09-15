# Review — ec2-only

Not a marketing page. What a human noticed after looking at the output.

## What worked
- VPC → Subnet → EC2 builds and prices in one command.
- `awsgraph explain "Backend EC2"` shows the assumptions behind the $75.92, not just the number.

## Simplifications in the pricing
- 730 h/month is entered by hand, not measured. A real instance stopped for a
  weekend costs less and nothing here would notice.
- The EC2 rate is a maintainer-entered list price. No Savings Plan, no free tier.

## Graph layout
- The design file has positions, so `graph.html` honours them. A design written
  without a `layout` block gets auto-placed by containment depth instead.

## Not supported yet
- No EBS root volume: the instance is priced as if its storage were free. Real
  EC2 instances almost always carry a gp3 root volume, so this total is low.

## Next version
- Model the root volume by default, or warn when an EC2 has no attached EBS.
