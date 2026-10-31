/** Lineage drill-down — Flink-style UI lineage walk (issue #566, docs 02).

From any conclusion node, ≤3 clicks reach raw evidence:
canvas node → detail drawer (claim, posterior, verify_tier, evidence refs)
→ original session excerpt / sha256 evidence 原文.

The rule holds for every historical version — snapshots preserve their own
evidence references (#548 A7). The LineageDrillDown resolves the path
mechanically from the version store; no streaming framework (克制清单).

Click semantics: 1 = canvas node (select the claim), 2 = detail drawer
(open the claim's snapshot context), 3 = raw evidence (the sha256-referenced
source document).
*/

import type { VersionStore } from "../versions/store.js";

export interface LineageStep {
  layer: "canvas-node" | "detail-drawer" | "raw-evidence";
  detail: Record<string, unknown>;
}

export interface LineagePath {
  clicks: number;
  steps: LineageStep[];
  raw_evidence?: { refs: string[]; report: Record<string, unknown> | null };
}

export class LineageDrillDown {
  constructor(private readonly versions: VersionStore) {}

  /** Resolve the ≤3-click lineage path from a committed version snapshot. */
  resolve(taskId: string, v: number, claimId: string): LineagePath | null {
    const version = this.versions.getVersion(taskId, v);
    if (version === null) {
      return null;
    }
    const claims = (version.snapshot.claims ?? []) as Array<{ id: string; text: string; posterior?: number; [key: string]: unknown }>;
    const claim = claims.find((c) => c.id === claimId);
    if (claim === undefined) {
      return null;
    }
    const evidenceRefs = version.snapshot.evidence_refs ?? [];
    return {
      clicks: 3,
      steps: [
        { layer: "canvas-node", detail: { claim_id: claimId, task_id: taskId, version: v } },
        { layer: "detail-drawer", detail: { claim, posterior: claim.posterior, verify_tier: (claim as Record<string, unknown>).verify_tier ?? "unknown" } },
        { layer: "raw-evidence", detail: { evidence_refs: evidenceRefs, report: version.snapshot.report ?? null } },
      ],
      raw_evidence: { refs: evidenceRefs, report: (version.snapshot.report as Record<string, unknown>) ?? null },
    };
  }
}
