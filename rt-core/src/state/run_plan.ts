/** Run-plan interpreter — plan = data; execution is mechanical (issue #551).

The plan declares stages (kill-graph factor clusters, consumed by the #550
scheduler), the global budget (12h hard cap invariant), and the yaw-check
slots (plan-level auto / problem-level human-sign / knowledge-level auto —
full detectors land with later waves; the slots exist from T0).

The interpreter validates the shape and tracks per-step advancement;
the pi loop (#552) drives it.
*/

import { LedgerIntegrityError } from "../store/integrity.js";

export const YAW_MODES = ["auto", "human"] as const;
export type YawMode = (typeof YAW_MODES)[number];
export const YAW_SLOTS = ["plan-level", "problem-level", "knowledge-level"] as const;
export type YawSlot = (typeof YAW_SLOTS)[number];

/** 12h hard cap — the product invariant from docs 04 (预算硬帽 12h/-run). */
export const BUDGET_CAP_MS = 12 * 3600 * 1000;

export interface RunPlanStage {
  id: string;
  title: string;
  claim_ids: string[];
  depends_on?: string[];
}

export interface RunPlan {
  plan_id: string;
  stages: RunPlanStage[];
  budget: { capMs: number };
  yaw_checks: Array<{ slot: YawSlot; mode: YawMode }>;
  // interpreter state
  steps?: Map<string, "pending" | "advanced" | "complete">;
}

export function parseRunPlan(raw: unknown): RunPlan {
  if (raw === null || typeof raw !== "object") {
    throw new LedgerIntegrityError("run plan must be a mapping");
  }
  const plan = raw as Record<string, unknown>;
  if (typeof plan.plan_id !== "string" || plan.plan_id === "") {
    throw new LedgerIntegrityError('field "plan_id" must be a non-empty string');
  }
  if (!Array.isArray(plan.stages)) {
    throw new LedgerIntegrityError('field "stages" must be a list');
  }
  const budget = plan.budget as Record<string, unknown> | undefined;
  if (
    budget === undefined ||
    typeof budget.capMs !== "number" ||
    budget.capMs <= 0 ||
    budget.capMs > BUDGET_CAP_MS
  ) {
    throw new LedgerIntegrityError(
      `field "budget.capMs" must be within the 12h product cap (${BUDGET_CAP_MS}ms)`,
    );
  }
  if (!Array.isArray(plan.yaw_checks)) {
    throw new LedgerIntegrityError('field "yaw_checks" must be a list');
  }
  const yaw_checks = plan.yaw_checks.map((check) => {
    const entry = check as Record<string, unknown>;
    if (!YAW_SLOTS.includes(entry.slot as YawSlot)) {
      throw new LedgerIntegrityError(`field "slot" must be one of ${JSON.stringify(YAW_SLOTS)}`);
    }
    if (!YAW_MODES.includes(entry.mode as YawMode)) {
      throw new LedgerIntegrityError(`field "mode" must be one of ${JSON.stringify(YAW_MODES)}`);
    }
    return { slot: entry.slot as YawSlot, mode: entry.mode as YawMode };
  });
  const stages = plan.stages.map((stage) => {
    const entry = stage as Record<string, unknown>;
    if (typeof entry.id !== "string" || entry.id === "") {
      throw new LedgerIntegrityError('field "id" must be a non-empty string');
    }
    return {
      id: entry.id,
      title: typeof entry.title === "string" ? entry.title : entry.id,
      claim_ids: Array.isArray(entry.claim_ids) ? (entry.claim_ids as string[]) : [],
      depends_on: Array.isArray(entry.depends_on) ? (entry.depends_on as string[]) : [],
    };
  });
  return {
    plan_id: plan.plan_id,
    stages,
    budget: { capMs: budget!.capMs as number },
    yaw_checks,
    steps: new Map(stages.map((stage) => [stage.id, "pending" as const])),
  };
}

/** Post-parse invariants beyond shape. */
export function validateRunPlan(plan: RunPlan): string[] {
  const issues: string[] = [];
  if (plan.budget.capMs <= 0 || plan.budget.capMs > BUDGET_CAP_MS) {
    issues.push("budget-cap");
  }
  const slotSet = new Set(plan.yaw_checks.map((check) => check.slot));
  for (const slot of YAW_SLOTS) {
    if (!slotSet.has(slot)) {
      issues.push(`yaw-slot:${slot}`);
    }
  }
  return issues;
}

/** Mechanical step advancement on a parsed plan. */
export class RunPlanInterpreter {
  constructor(private readonly plan: RunPlan) {
    if (this.plan.steps === undefined) {
      this.plan.steps = new Map(this.plan.stages.map((stage) => [stage.id, "pending" as const]));
    }
  }

  advance(stageId: string): void {
    this.requireStage(stageId);
    this.plan.steps!.set(stageId, "advanced");
  }

  complete(stageId: string): void {
    this.requireStage(stageId);
    this.plan.steps!.set(stageId, "complete");
  }

  stepStatus(stageId: string): "pending" | "advanced" | "complete" {
    this.requireStage(stageId);
    return this.plan.steps!.get(stageId)!;
  }

  private requireStage(stageId: string): void {
    if (!this.plan.steps!.has(stageId)) {
      throw new LedgerIntegrityError(`unknown plan stage: ${stageId}`);
    }
  }
}
