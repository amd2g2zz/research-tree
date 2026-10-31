/** Experiment layer v1 (issue #567, docs 01 L4 + #567).

Pre-registration before execution: hypothesis / discriminating criterion /
minimum sample / cost cap — registered first, run second. **Designer ≠
executor**: a fresh-context independent subagent executes (anti-rigged).
Tier ladder hard gates: over-budget claims land experiment-gated into the
risk register, not run. Sequential stop (SPRT-style): posterior past
threshold stops the experiment.

Experiments persist via the #547 experiments table (preregistration JSON,
stop state, cost). The execution runner is injectable (the actual benchmark
execution is host-side / pi-subagents).
*/

import type { LedgerStore } from "../store/ledger.js";
import { LedgerIntegrityError } from "../store/integrity.js";

export interface ExperimentRegistration {
  experiment_id: string;
  hypothesis: string;
  method: string;
  criterion: string;
  min_sample: number;
  cost_cap: number;
  designer: string;
}

export interface ExperimentRecord {
  experiment_id: string;
  status: "registered" | "running" | "stopped" | "gated";
  preregistration: Record<string, unknown>;
  stop_state: Record<string, unknown> | null;
  cost: number | null;
}

export interface ExecutionOptions {
  executor: string;
}

export interface ObservationResult {
  stopped: boolean;
  reason?: string;
  posterior: number;
  sample: number;
}

const POSTERIOR_STOP_THRESHOLD = 0.95;

export class ExperimentLayer {
  constructor(private readonly ledger: LedgerStore) {}

  /** Pre-register: hypothesis/criterion/min-sample/cost-cap registered FIRST. */
  register(taskId: string, payload: ExperimentRegistration): Record<string, unknown> {
    if (payload.hypothesis === "" || payload.criterion === "") {
      throw new LedgerIntegrityError("preregistration requires hypothesis and criterion");
    }
    if (payload.min_sample <= 0) {
      throw new LedgerIntegrityError('field "min_sample" must be >= 1');
    }
    if (payload.cost_cap <= 0) {
      throw new LedgerIntegrityError('field "cost_cap" must be > 0');
    }
    this.ledger.upsertExperiment(taskId, {
      experiment_id: payload.experiment_id,
      status: "registered",
      preregistration: {
        hypothesis: payload.hypothesis,
        method: payload.method,
        criterion: payload.criterion,
        min_sample: payload.min_sample,
        cost_cap: payload.cost_cap,
        designer: payload.designer,
      },
      stop_state: null,
      cost: null,
    });
    return this.ledger.getExperiment(taskId, payload.experiment_id) as unknown as Record<string, unknown>;
  }

  /** Execute: designer ≠ executor enforced (anti-rigged). */
  async execute(experimentId: string, options: ExecutionOptions): Promise<Record<string, unknown>> {
    const row = this.getExperiment(experimentId);
    const prereg = row.preregistration as { designer?: string };
    if (prereg.designer === options.executor) {
      throw new LedgerIntegrityError(
        `designer ≠ executor violated: ${options.executor} designed and executes ${experimentId}`,
      );
    }
    this.ledger.upsertExperiment(String(row.task_id ?? "t1"), {
      experiment_id: experimentId,
      status: "running",
      preregistration: prereg,
      stop_state: null,
      cost: 0,
    });
    return this.getExperiment(experimentId) as unknown as Record<string, unknown>;
  }

  /** Sequential stop (SPRT-style): posterior past threshold stops. */
  recordObservation(experimentId: string, observation: { posterior: number; sample: number }): ObservationResult {
    const row = this.getExperiment(experimentId)!;
    const prereg = row.preregistration as { min_sample?: number };
    const minSample = Number(prereg.min_sample ?? 1);
    const stopped = observation.posterior >= POSTERIOR_STOP_THRESHOLD && observation.sample >= minSample;
    if (stopped) {
      this.ledger.upsertExperiment(row.task_id as string, {
        experiment_id: experimentId,
        status: "stopped",
        preregistration: prereg,
        stop_state: { reason: "posterior-past-threshold", posterior: observation.posterior, sample: observation.sample },
        cost: row.cost as number | null,
      });
    }
    return { stopped, reason: stopped ? "posterior-past-threshold" : undefined, posterior: observation.posterior, sample: observation.sample };
  }

  /** Budget check: over-budget claims land experiment-gated (not run). */
  checkBudget(experimentId: string, input: { estimated_cost: number }): { experiment_gated: boolean; reason: string } {
    const row = this.getExperiment(experimentId)!;
    const prereg = row.preregistration as { cost_cap?: number };
    if (input.estimated_cost > Number(prereg.cost_cap)) {
      this.ledger.upsertExperiment(row.task_id as string, {
        experiment_id: experimentId,
        status: "gated",
        preregistration: prereg,
        stop_state: null,
        cost: null,
      });
      return { experiment_gated: true, reason: "estimated cost exceeds the registered cost cap" };
    }
    return { experiment_gated: false, reason: "within cap" };
  }

  private getExperiment(experimentId: string): Record<string, unknown> {
    // the task scoping is internal — search all tasks for the id
    const row = this.ledger.connection
      .prepare("SELECT * FROM experiments WHERE experiment_id = ? LIMIT 1")
      .get(experimentId) as Record<string, unknown> | undefined;
    if (row === undefined) {
      throw new LedgerIntegrityError(`experiment not found: ${experimentId}`);
    }
    const record = { ...row };
    for (const column of ["preregistration", "stop_state"]) {
      if (record[column] !== null && record[column] !== undefined) {
        record[column] = JSON.parse(String(record[column]));
      }
    }
    return record;
  }
}
