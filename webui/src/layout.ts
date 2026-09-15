import type { Architecture } from "./types";

const COLUMN = 210;
const ROW = 130;

/**
 * Place resources that the design file has no coordinates for. Same longest-path
 * ranking the viewer uses, so a hand-written .awsgraph.json opens readable
 * instead of stacked in one column.
 */
export function placeMissing(architecture: Architecture): Record<string, { x: number; y: number }> {
  const stored = architecture.layout.positions;
  const missing = architecture.resources.filter((r) => !stored[r.id]);
  if (missing.length === 0) return stored;

  const rank = new Map(architecture.resources.map((r) => [r.id, 0]));
  for (let pass = 0; pass < architecture.resources.length; pass++) {
    let changed = false;
    for (const edge of architecture.relationships) {
      const from = rank.get(edge.source);
      const to = rank.get(edge.target);
      if (from === undefined || to === undefined) continue;
      if (from + 1 > to) {
        rank.set(edge.target, from + 1);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const used = new Map<number, number>();
  const placed: Record<string, { x: number; y: number }> = { ...stored };
  for (const resource of missing) {
    const row = rank.get(resource.id) ?? 0;
    const column = used.get(row) ?? 0;
    used.set(row, column + 1);
    placed[resource.id] = { x: column * COLUMN, y: row * ROW };
  }
  return placed;
}
