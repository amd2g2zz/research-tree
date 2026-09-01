"""Projection success oracles for the senior-user-ux-v2 dual-track evaluation.

Issue #292 closes only when a fresh advanced-user run demonstrates its ten
acceptance gates.  This module is the mechanical half of that closure path
(#451 prep checklist): it turns each closure gate and follow-up metric into a
projection success oracle whose ``evidence_standard_ids`` name the evidence
vocabulary the run must produce, so a projection built through
``build_success_oracles()`` / ``build_decision_targets()`` passes
``validate_falsifiability`` and the run's completion gate judges the #292
gates oracle by oracle.  Gate attribution is prose-only metadata: the runtime
enforces per oracle, never per gate.  Oracle entries feed the projection's
authority fingerprint, so any statement or gate_ids edit invalidates existing
alignment verifications and handoff confirmations.

Pure data plus two builders; no runtime imports, no I/O.
"""

from __future__ import annotations

from typing import Any

RUN_NAME = "senior-user-ux-v2"
BASELINE_RUN_NAME = "senior-user-ux-20260820"

CLOSURE_GATES: tuple[int, ...] = tuple(range(1, 11))

# An evidence standard names one evidence vocabulary; a finding pack satisfies
# it when its corroborated claims carry matching tokens (grounding identities,
# provenance clusters, or grounding artifact ids).
EVIDENCE_STANDARDS: dict[str, dict[str, str]] = {
    "es-handoff-fingerprint-match": {
        "statement": (
            "Handoff authority fields are field-bound: the displayed authority fingerprint equals the "
            "fingerprint in the handoff_confirmed record and compilation re-materializes each field."
        ),
        "token_basis": (
            "authority fingerprint values, handoff/confirmation artifact ids, and canonical "
            "compile-block reasons from receipt records"
        ),
    },
    "es-completion-snapshot-digest": {
        "statement": (
            "One immutable completion snapshot feeds durable state, visible plan, reports, final "
            "response, test counts, exit codes, revisions, and artifact digests; cross-projection "
            "mismatches surface as delivery_pending or blocked, never a pass."
        ),
        "token_basis": (
            "completion snapshot digest values, delivery manifest/pair digests, and mismatch-block receipt ids"
        ),
    },
    "es-verifier-identity-distinct": {
        "statement": (
            "Every required review records a distinct verifier execution identity, session lineage, "
            "evidence custody, oracle custody, and authority; self-issued verification artifacts are "
            "rejected."
        ),
        "token_basis": (
            "alignment-verification and delivery-review artifact ids plus verify_identity_independent "
            "pass records; custody covers the evidence packs and the oracle definitions the verdicts bind"
        ),
    },
    "es-host-conformance-receipt": {
        "statement": (
            "install, doctor, run, resume, status, and verify accept ordinary operator inputs without "
            "exposing internal schemas, and copy-install is followed by status-current returning "
            "current for each of Codex, Claude Code, and Hermes."
        ),
        "token_basis": "per-host host-conformance receipt artifact ids and payload_digest_match records",
    },
    "es-slot-closure-record": {
        "statement": (
            "Each high-impact decision holds a stable unique slot identity with a closure result; "
            "serial ordering appears only with an explicit evidence or data dependency; unused safe "
            "concurrency is reported."
        ),
        "token_basis": "decision slot ids, slot closure assessment artifact ids, and concurrency report records",
    },
    "es-budget-receipt": {
        "statement": (
            "Receipts report fresh, cached, and replayed reads with source digests or ranges, "
            "tool/process output volume, duplicate-read ratio, active-output sealing, and budget "
            "state; an exhausted budget ends in a resumable unknown checkpoint, never a pass."
        ),
        "token_basis": (
            "budget/freshness receipt artifact ids carrying fresh/cached/replayed counts, duplicate "
            "ratios, and sealing records"
        ),
    },
    "es-noise-measurement": {
        "statement": (
            "User-visible repeated output and reread behavior are measured against the baseline run "
            "with an explicit counting basis and the measurement is archived in the v2 run record."
        ),
        "token_basis": (
            "baseline-comparison measurement record ids (duplicate-output counts, reread audit rows) "
            "and the budget receipts they cite"
        ),
    },
    "es-host-matrix-receipt": {
        "statement": (
            "The six-scenario by three-host injection matrix yields reachable canonical receipts for "
            "every cell with per-cell provenance and host-invocation disclosure."
        ),
        "token_basis": "host-matrix receipt artifact ids (18 passed cells) and per-cell provenance records",
    },
    "es-operating-model-payload": {
        "statement": (
            "The v2 Human Research Report exposes roles, SLA, concurrency limits, blockers with "
            "owners, outcome layers, adoption metrics, and a fallback plan, every field populated "
            "from run artifacts with no placeholders."
        ),
        "token_basis": "operating_model delivery payload artifact refs and its validator records",
    },
    "es-freshness-decision-record": {
        "statement": (
            "An implementation baseline that lags the intended integration revision blocks admission "
            "or forces revalidation; no stale baseline is footnoted into a pass."
        ),
        "token_basis": "freshness admission decision records and the freshness gate receipts they cite",
    },
    "es-role-transcript": {
        "statement": (
            "Each Track A role archives an independent transcript, report, and machine-readable "
            "summary under the v2 run name, scored under the 8/20 protocol with scores kept separate."
        ),
        "token_basis": "per-role transcript/report/summary.json artifact ids archived under senior-user-ux-v2",
    },
    "es-boundary-disclosure": {
        "statement": (
            "Every projection distinguishes executed, prototype/package, replayed, and missing "
            "evidence; no missing external source or incomplete host path is promoted to success."
        ),
        "token_basis": "finding-pack boundary and limitation disclosure records with evidence_class fields",
    },
    "es-recovery-reason-record": {
        "statement": (
            "Every injected failure resolves to its canonical failure semantic with zero promotions "
            "of a failed attempt to success and no false completion declarations."
        ),
        "token_basis": "canonical failure reason strings and zero-mutation assertions from injection receipts",
    },
}

SUCCESS_ORACLES: tuple[dict[str, Any], ...] = (
    {
        "id": "oracle-handoff-integrity",
        "statement": (
            "Every handoff compiled in the v2 run binds outcome, scope, authority, success oracles, "
            "and confirmation revision as fields, and any single-field mismatch blocks compilation "
            "before execution (zero compiled handoffs with drifted authority fields)."
        ),
        "gate_ids": (1,),
        "evidence_standard_ids": ("es-handoff-fingerprint-match",),
    },
    {
        "id": "oracle-completion-consistency",
        "statement": (
            "Durable completion state, visible plan, reports, final response, test counts, exit "
            "codes, revisions, and artifact digests derive from one immutable snapshot throughout "
            "the v2 run; any mismatch renders the run delivery_pending or blocked, never passed."
        ),
        "gate_ids": (2, 10),
        "evidence_standard_ids": ("es-completion-snapshot-digest",),
    },
    {
        "id": "oracle-independent-review",
        "statement": (
            "Every display and delivery gate in the v2 run is satisfied by an independent-subagent "
            "verification artifact with distinct identity and session lineage, and at least one "
            "self-issued artifact is demonstrably rejected."
        ),
        "gate_ids": (3,),
        "evidence_standard_ids": ("es-verifier-identity-distinct",),
    },
    {
        "id": "oracle-operator-lifecycle",
        "statement": (
            "All six lifecycle commands accept ordinary operator inputs and hide internal schemas on "
            "all three hosts, with copy-install followed by status-current returning current for "
            "Codex, Claude Code, and Hermes."
        ),
        "gate_ids": (4,),
        "evidence_standard_ids": ("es-host-conformance-receipt",),
    },
    {
        "id": "oracle-slot-decomposition",
        "statement": (
            "The v2 run preserves decision decomposition: every high-impact decision keeps a stable "
            "unique slot identity and closure result, serial dependencies each cite an evidence or "
            "data dependency, and unused safe concurrency is reported rather than silently dropped."
        ),
        "gate_ids": (5,),
        "evidence_standard_ids": ("es-slot-closure-record",),
    },
    {
        "id": "oracle-context-discipline",
        "statement": (
            "Every v2 receipt reports fresh/cached/replayed reads, source digests or ranges, "
            "tool/process output, duplicate ratio, and sealing state, and an exhausted budget "
            "produces a resumable unknown checkpoint rather than a pass."
        ),
        "gate_ids": (6,),
        "evidence_standard_ids": ("es-budget-receipt",),
    },
    {
        "id": "oracle-noise-reduction",
        "statement": (
            "User-visible repeated output across the v2 run is at least 70% below the "
            "senior-user-ux-20260820 baseline at equal task coverage, and no already-confirmed "
            "material is reread within a bounded run unless its source digest or decision scope "
            "changed."
        ),
        "gate_ids": (10,),
        "evidence_standard_ids": ("es-noise-measurement", "es-budget-receipt"),
    },
    {
        "id": "oracle-live-host-matrix",
        "statement": (
            "The six-scenario by three-host failure-injection matrix yields reachable canonical "
            "receipts for all eighteen cells, each with per-cell provenance and explicit "
            "host-invocation disclosure."
        ),
        "gate_ids": (7,),
        "evidence_standard_ids": ("es-host-matrix-receipt",),
    },
    {
        "id": "oracle-operating-model",
        "statement": (
            "The v2 Human Research Report operates as an operating model: roles, SLA, concurrency "
            "limits, owner-mapped blockers, outcome layers, adoption metrics, and fallback plans "
            "are present and populated from run artifacts with zero placeholders."
        ),
        "gate_ids": (8,),
        "evidence_standard_ids": ("es-operating-model-payload",),
    },
    {
        "id": "oracle-freshness-gate",
        "statement": (
            "The v2 run admits only an implementation baseline at the intended integration revision: "
            "a lagging baseline blocks the admission bundle or forces revalidation instead of "
            "becoming a footnote."
        ),
        "gate_ids": (9,),
        "evidence_standard_ids": ("es-freshness-decision-record",),
    },
    {
        "id": "oracle-alignment-regression",
        "statement": (
            "All three Track A roles re-run the full journey under the 8/20 protocol with scores "
            "kept separate, and their alignment narratives (confusion handled as "
            "teaching/reconnaissance signal, explicit outcome/scope/authority/oracle/confirmation "
            "before handoff) show no regression against the baseline role reports."
        ),
        "gate_ids": (10,),
        "evidence_standard_ids": ("es-role-transcript",),
    },
    {
        "id": "oracle-evidence-honesty",
        "statement": (
            "Every v2 projection keeps evidence boundaries honest: executed, prototype/package, "
            "replayed, and missing evidence stay distinguishable, and no missing external source or "
            "incomplete host path is promoted to success."
        ),
        "gate_ids": (10,),
        "evidence_standard_ids": ("es-boundary-disclosure",),
    },
    {
        "id": "oracle-recovery-semantics",
        "statement": (
            "Every injected or naturally occurring failure in the v2 run resolves to its canonical "
            "failure semantic (unknown on interruption, stale-child rejection, tamper detection, "
            "workspace isolation) with zero failed attempts promoted to success."
        ),
        "gate_ids": (7, 10),
        "evidence_standard_ids": ("es-recovery-reason-record", "es-host-matrix-receipt"),
    },
)

DECISION_TARGETS: tuple[dict[str, Any], ...] = (
    {
        "id": "decision-track-a-ux-verdict",
        "statement": "Track A: the 8/20 conditional-use UX verdict holds with no alignment or evidence-honesty regression and materially lower noise.",
        "oracle_ids": (
            "oracle-alignment-regression",
            "oracle-evidence-honesty",
            "oracle-completion-consistency",
            "oracle-noise-reduction",
            "oracle-operator-lifecycle",
            "oracle-slot-decomposition",
        ),
    },
    {
        "id": "decision-track-b-runtime-verdict",
        "statement": "Track B: the governed runtime survives live failure injection with the goal loop closed and no fail-open.",
        "oracle_ids": (
            "oracle-handoff-integrity",
            "oracle-independent-review",
            "oracle-live-host-matrix",
            "oracle-recovery-semantics",
            "oracle-context-discipline",
            "oracle-slot-decomposition",
            "oracle-completion-consistency",
        ),
    },
    {
        "id": "decision-adoption-upgrade",
        "statement": "The #292 conditional-adoption verdict may be upgraded once every acceptance gate carries fresh v2 evidence.",
        "oracle_ids": tuple(oracle["id"] for oracle in SUCCESS_ORACLES),
    },
)

# The follow-up metric list recorded in #292 ("Metrics for the follow-up
# evaluation"), each mapped to the oracles that carry it.  Counting basis:
# 1 role-score rule + 12 tracked metrics + 1 noise criterion = 14 rows.
METRIC_COVERAGE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("alignment quality", ("oracle-alignment-regression",)),
    ("evidence-boundary honesty", ("oracle-evidence-honesty",)),
    ("recovery semantics", ("oracle-recovery-semantics",)),
    ("installation success", ("oracle-operator-lifecycle",)),
    ("lifecycle ergonomics", ("oracle-operator-lifecycle",)),
    ("independent-review validity", ("oracle-independent-review",)),
    ("completion consistency", ("oracle-completion-consistency",)),
    ("unique decision-slot closure", ("oracle-slot-decomposition",)),
    ("duplicate-read ratio", ("oracle-context-discipline", "oracle-noise-reduction")),
    ("fresh/cached/replayed input", ("oracle-context-discipline",)),
    ("tool/process output", ("oracle-context-discipline",)),
    ("live-host receipt coverage", ("oracle-live-host-matrix",)),
    (
        "role scores kept separate without undeclared normalization",
        ("oracle-alignment-regression",),
    ),
    (
        "at-least-70% repeated-output reduction with no confirmed-material reread",
        ("oracle-noise-reduction",),
    ),
)


def build_success_oracles() -> tuple[dict[str, Any], ...]:
    """Oracle entries for ``StrategyProjection.create(success_oracles=...)``."""

    return tuple(
        {
            "id": oracle["id"],
            "statement": oracle["statement"],
            "gate_ids": tuple(oracle["gate_ids"]),
            "evidence_standard_ids": tuple(oracle["evidence_standard_ids"]),
        }
        for oracle in SUCCESS_ORACLES
    )


def build_decision_targets() -> tuple[dict[str, Any], ...]:
    """Decision-target entries for ``StrategyProjection.create(decision_targets=...)``."""

    return tuple(
        {
            "id": target["id"],
            "statement": target["statement"],
            "oracle_ids": tuple(target["oracle_ids"]),
        }
        for target in DECISION_TARGETS
    )
