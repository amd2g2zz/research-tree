"""Deterministically verify whether a technical package is ready for handoff."""

from __future__ import annotations

import ast
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from .decision_map import BLUEPRINT_TARGET_KIND
from .delivery import TECHNICAL_RESEARCH_PACKAGE_KIND, validate_technical_package_payload
from .domain import (
    ArtifactRef,
    ArtifactRevision,
    InvalidIdentifierError,
    RuntimeStoreError,
    thaw_json,
    validate_identifier,
)
from .intent import INTENT_MODEL_KIND, WORKING_BRIEF_KIND
from .ledger import DECISION_LEDGER_KIND, FINDING_PACK_KIND
from .evidence import EvidenceAnchor, EvidenceResolver, EvidenceValidationError
from .contradictions import (
    blocking_contradictions,
    claim_from_mapping,
    invalidating_contradictions,
    unresolved_claim_ids,
)
from .run_ledger import RunLedger
from .verification import (
    FAILURE_CATEGORY_GATES,
    InvalidVerificationError,
    IsolatedVerificationAdapter,
    RiskVerificationAssessment,
    assess_risk_verification,
    validate_risk_verification_payload,
)


READINESS_RECORD_KIND = "readiness-record"
MAX_SYMBOL_CHECK_BYTES = 1_000_000
RISK_TIERS = {"default", "medium", "high"}
READINESS_GATES = (
    "intent_alignment",
    "decision_closure",
    "traceability",
    "repository_fit",
    "implementation_readiness",
    "operational_quality",
)
GATE_STATES = {
    "intent_alignment": {"pass", "fail", "deferred"},
    "decision_closure": {"pass", "fail", "deferred"},
    "traceability": {"pass", "fail"},
    "repository_fit": {"pass", "fail", "not_applicable"},
    "implementation_readiness": {"pass", "fail", "deferred"},
    "operational_quality": {"pass", "fail", "deferred"},
}
class ReadinessError(RuntimeStoreError):
    """Base error for readiness verification inputs and records."""


class InvalidReadinessError(ReadinessError):
    """Raised before an invalid readiness record can be appended."""


class CanonicalReadinessVerifier:
    """Check an immutable technical package without changing its research target."""

    def __init__(
        self,
        ledger: RunLedger,
        evidence_resolver: EvidenceResolver,
    ) -> None:
        if not isinstance(ledger, RunLedger):
            raise InvalidReadinessError("canonical readiness requires a RunLedger")
        if not isinstance(evidence_resolver, EvidenceResolver) or evidence_resolver.ledger is not ledger:
            raise InvalidReadinessError(
                "canonical readiness requires a matching ledger-backed EvidenceResolver"
            )
        self._ledger = ledger
        self._evidence_resolver = evidence_resolver

    def verify(
        self,
        *,
        round_id: str,
        readiness_id: str,
        technical_package: ArtifactRevision,
        repository_roots: Mapping[str, str | Path] | None = None,
        risk_tier: str = "default",
        verification_adapter: IsolatedVerificationAdapter | None = None,
        expected_revision: int,
    ) -> ArtifactRevision:
        """Append one diagnostic readiness record for an exact package revision.

        ``repository_roots`` is deliberately an explicit caller-owned mapping.
        It is used only for bounded read-only anchor checks; baseline metadata is
        never treated as a live filesystem location.
        """

        try:
            snapshot = self._ledger.load_run(round_id)
            validate_identifier(readiness_id, "readiness_id")
            _ensure_id_compatibility(snapshot.artifacts, readiness_id)
            tier = _enum(risk_tier, "risk_tier", RISK_TIERS)
            package = _resolve_exact(
                snapshot.artifacts,
                technical_package,
                TECHNICAL_RESEARCH_PACKAGE_KIND,
                "technical_package",
            )
            if package.round_id != round_id:
                raise InvalidReadinessError("technical_package must belong to readiness round")
            try:
                validate_technical_package_payload(package.payload)
            except RuntimeStoreError as error:
                raise InvalidReadinessError(
                    f"technical_package payload is invalid: {error}"
                ) from error
            document = _mapping(package.payload["document"], "technical_package document")
            sources = _resolve_package_sources(snapshot.artifacts, package, document)
            root_map = _normalize_repository_roots(repository_roots, sources["repositories"])
            diagnostics, checks, gate_states = _evaluate_package(
                document,
                sources,
                root_map,
                tier,
                evidence_resolver=self._evidence_resolver,
            )
            assessment = assess_risk_verification(
                round_id=round_id,
                risk_tier=tier,
                technical_package=package,
                repositories=sources["repositories"],
                adapter=verification_adapter,
            )
            risk_verification = _apply_risk_verification(
                assessment,
                snapshot.artifacts,
                slots=_slots(sources["target"]),
                records={
                    _identifier(item.get("decision_slot_id"), "decision_record decision_slot_id"): item
                    for item in _mappings(document["decision_records"], "decision_records")
                },
                diagnostics=diagnostics,
                gate_states=gate_states,
            )
            delivery_readiness = _delivery_projection(tier, gate_states, diagnostics)
            payload = {
                "technical_package_ref": _ref_dict(package),
                "delivery_readiness": delivery_readiness,
                "diagnostics": diagnostics,
                "repository_anchor_checks": checks,
                "source_refs": [_ref_dict(artifact) for artifact in sources["artifacts"]],
                "risk_verification": risk_verification,
            }
            validate_readiness_record_payload(payload)
        except (InvalidIdentifierError, InvalidVerificationError, TypeError, ValueError) as error:
            raise InvalidReadinessError(str(error)) from error

        parent_refs = _unique_refs(
            (ArtifactRef(round_id, package.id, package.revision),)
            + tuple(ArtifactRef(round_id, item.id, item.revision) for item in sources["artifacts"])
        )
        if not all(self._ledger.is_latest_artifact(reference) for reference in parent_refs):
            return self._ledger.append_artifact(
                round_id=round_id,
                readiness_id=readiness_id,
                payload=payload,
                parent_refs=parent_refs,
                expected_revision=expected_revision,
            )
        from .completion_inputs import CompletionInputRegistrar

        return CompletionInputRegistrar(self._ledger).write_readiness(
            round_id=round_id,
            readiness_id=readiness_id,
            payload=payload,
            parent_refs=parent_refs,
            expected_revision=expected_revision,
        )


def readiness_for_delivery(record: ArtifactRevision) -> Mapping[str, Any]:
    """Return the exact readiness mapping accepted by canonical delivery."""

    if not isinstance(record, ArtifactRevision) or record.kind != READINESS_RECORD_KIND:
        raise InvalidReadinessError("record must be a readiness-record ArtifactRevision")
    validate_readiness_record_payload(record.payload)
    projection = record.payload["delivery_readiness"]
    if not isinstance(projection, Mapping):
        raise InvalidReadinessError("delivery_readiness must be a mapping")
    return projection


def validate_readiness_record_payload(payload: Mapping[str, Any]) -> None:
    """Validate the public, persisted readiness record schema recursively."""

    legacy_keys = {
        "technical_package_ref",
        "delivery_readiness",
        "diagnostics",
        "repository_anchor_checks",
        "source_refs",
    }
    current_keys = legacy_keys | {"risk_verification"}
    actual_keys = set(payload)
    if frozenset(actual_keys) not in {frozenset(legacy_keys), frozenset(current_keys)}:
        raise InvalidReadinessError(
            "readiness record payload has unexpected keys; "
            f"missing={sorted(legacy_keys - actual_keys)}, extra={sorted(actual_keys - current_keys)}"
    )
    _validate_ref(payload["technical_package_ref"], "technical_package_ref")
    if "risk_verification" in payload:
        validate_risk_verification_payload(payload["risk_verification"])
        risk_evidence = _mapping(payload["risk_verification"], "risk_verification")
        risk_package = _mapping(
            risk_evidence["technical_package"], "risk_verification.technical_package"
        )
        if risk_package["ref"] != payload["technical_package_ref"]:
            raise InvalidReadinessError(
                "risk_verification technical package ref must match readiness technical_package_ref"
            )
    projection = _mapping(payload["delivery_readiness"], "delivery_readiness")
    _require_exact_keys(
        projection,
        {"risk_tier", "gates", "findings", "next_work_item_ids"},
        "delivery_readiness",
    )
    _enum(projection["risk_tier"], "delivery_readiness.risk_tier", RISK_TIERS)
    gates = _mapping(projection["gates"], "delivery_readiness.gates")
    _require_exact_keys(gates, set(READINESS_GATES), "delivery_readiness.gates")
    for gate in READINESS_GATES:
        _enum(gates[gate], f"delivery_readiness.gates.{gate}", GATE_STATES[gate])
    for index, finding in enumerate(_mappings(projection["findings"], "delivery_readiness.findings")):
        label = f"delivery_readiness.findings[{index}]"
        _require_exact_keys(finding, {"gate", "summary"}, label)
        _enum(finding["gate"], f"{label}.gate", set(READINESS_GATES))
        _nonempty(finding["summary"], f"{label}.summary")
    _identifiers(projection["next_work_item_ids"], "delivery_readiness.next_work_item_ids")

    expected_diagnostics = _mappings(payload["diagnostics"], "diagnostics")
    for index, diagnostic in enumerate(expected_diagnostics):
        label = f"diagnostics[{index}]"
        legacy_diagnostic_keys = {
            "gate",
            "status",
            "summary",
            "decision_slot_id",
            "decision_id",
            "work_item_id",
            "recommended_work",
        }
        current_diagnostic_keys = legacy_diagnostic_keys | {"failure_category"}
        diagnostic_keys = set(diagnostic)
        if frozenset(diagnostic_keys) not in {
            frozenset(legacy_diagnostic_keys),
            frozenset(current_diagnostic_keys),
        }:
            raise InvalidReadinessError(
                f"{label} has unexpected keys; missing={sorted(legacy_diagnostic_keys - diagnostic_keys)}, "
                f"extra={sorted(diagnostic_keys - current_diagnostic_keys)}"
            )
        gate = _enum(diagnostic["gate"], f"{label}.gate", set(READINESS_GATES))
        _enum(diagnostic["status"], f"{label}.status", GATE_STATES[gate] - {"pass"})
        _nonempty(diagnostic["summary"], f"{label}.summary")
        for field in ("decision_slot_id", "decision_id", "work_item_id"):
            if diagnostic[field] is not None:
                _identifier(diagnostic[field], f"{label}.{field}")
        failure_category = diagnostic.get("failure_category")
        if failure_category is not None:
            _enum(
                failure_category,
                f"{label}.failure_category",
                set(FAILURE_CATEGORY_GATES),
            )
        _validate_recommended_work(diagnostic["recommended_work"], f"{label}.recommended_work")
        if diagnostic["status"] != "fail" and diagnostic["recommended_work"] is not None:
            raise InvalidReadinessError(
                f"{label}.recommended_work is only allowed for failing gates"
            )

    for index, check in enumerate(_mappings(payload["repository_anchor_checks"], "repository_anchor_checks")):
        label = f"repository_anchor_checks[{index}]"
        _require_exact_keys(check, {"input_id", "path", "symbol", "resolved", "reason"}, label)
        _identifier(check["input_id"], f"{label}.input_id")
        _nonempty(check["path"], f"{label}.path")
        if check["symbol"] is not None:
            _nonempty(check["symbol"], f"{label}.symbol")
        if not isinstance(check["resolved"], bool):
            raise InvalidReadinessError(f"{label}.resolved must be a boolean")
        _nonempty(check["reason"], f"{label}.reason")
    source_refs = {
        _artifact_ref(ref, f"source_refs[{index}]")
        for index, ref in enumerate(_mappings(payload["source_refs"], "source_refs"))
    }
    if "risk_verification" in payload:
        risk_evidence = _mapping(payload["risk_verification"], "risk_verification")
        baseline_refs = [
            _artifact_ref(baseline["input_ref"], f"risk_verification.baselines[{index}].input_ref")
            for index, baseline in enumerate(
                _mappings(risk_evidence["baselines"], "risk_verification.baselines")
            )
        ]
        if len(set(baseline_refs)) != len(baseline_refs):
            raise InvalidReadinessError("risk_verification baselines must not repeat an input ref")
        if not set(baseline_refs) <= source_refs:
            raise InvalidReadinessError(
                "risk_verification baseline refs must belong to the readiness source refs"
            )


def _resolve_package_sources(
    artifacts: Sequence[ArtifactRevision],
    package: ArtifactRevision,
    document: Mapping[str, Any],
) -> dict[str, Any]:
    traceability = _mapping(document.get("traceability"), "technical package traceability")
    required = {"working_brief", "intent_model", "blueprint_target", "input_refs", "decision_refs", "finding_refs"}
    _require_exact_keys(traceability, required, "technical package traceability")
    by_ref = {(item.id, item.revision): item for item in artifacts}

    def resolve(ref_value: Any, expected_kind: str, label: str) -> ArtifactRevision:
        ref = _artifact_ref(ref_value, label)
        item = by_ref.get((ref.artifact_id, ref.revision))
        if item is None or item.round_id != package.round_id or item.kind != expected_kind:
            raise InvalidReadinessError(f"{label} does not resolve to an exact {expected_kind}")
        if ref not in package.parent_refs:
            raise InvalidReadinessError(f"technical_package lacks parent lineage for {label}")
        return item

    brief = resolve(traceability["working_brief"], WORKING_BRIEF_KIND, "working_brief")
    model = resolve(traceability["intent_model"], INTENT_MODEL_KIND, "intent_model")
    target = resolve(traceability["blueprint_target"], BLUEPRINT_TARGET_KIND, "blueprint_target")
    inputs = [
        resolve(ref, "input-ledger-entry", f"input_refs[{index}]")
        for index, ref in enumerate(_mappings(traceability["input_refs"], "input_refs"))
    ]
    decisions = [
        resolve(ref, DECISION_LEDGER_KIND, f"decision_refs[{index}]")
        for index, ref in enumerate(_mappings(traceability["decision_refs"], "decision_refs"))
    ]
    findings = [
        resolve(ref, FINDING_PACK_KIND, f"finding_refs[{index}]")
        for index, ref in enumerate(_mappings(traceability["finding_refs"], "finding_refs"))
    ]
    if target.payload.get("brief_id") != brief.id or target.payload.get("intent_model_id") != model.id:
        raise InvalidReadinessError("Blueprint Target does not match package Brief and Intent Model")
    return {
        "brief": brief,
        "model": model,
        "target": target,
        "inputs": tuple(inputs),
        "decisions": tuple(decisions),
        "findings": tuple(findings),
        "repositories": tuple(
            item for item in inputs if item.payload.get("kind") == "repository"
        ),
        "artifacts": (brief, model, target, *inputs, *decisions, *findings),
    }


def _normalize_repository_roots(
    value: Mapping[str, str | Path] | None,
    repositories: Sequence[ArtifactRevision],
) -> dict[str, Path]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise InvalidReadinessError("repository_roots must be a mapping")
    expected = {item.id for item in repositories}
    actual = {_identifier(key, "repository_roots key") for key in value}
    if actual != expected:
        raise InvalidReadinessError(
            f"repository_roots must cover exactly package repository inputs; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    roots: dict[str, Path] = {}
    for input_id in sorted(expected):
        root = Path(value[input_id]).expanduser().resolve(strict=False)
        if not root.is_dir():
            raise InvalidReadinessError(f"repository_roots[{input_id}] is not a readable directory")
        roots[input_id] = root
    return roots


def _evaluate_package(
    document: Mapping[str, Any],
    sources: Mapping[str, Any],
    roots: Mapping[str, Path],
    tier: str,
    *,
    evidence_resolver: EvidenceResolver | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    target = sources["target"]
    slots = _slots(target)
    records = {
        _identifier(item.get("decision_slot_id"), "decision_record decision_slot_id"): item
        for item in _mappings(document["decision_records"], "decision_records")
    }
    closures = {
        _identifier(item.get("decision_slot_id"), "blueprint_closure decision_slot_id"): item
        for item in _mappings(document["blueprint_closure"], "blueprint_closure")
    }
    ledger_by_slot = _index_ledgers(sources["decisions"])
    _ensure_package_decision_lineage(slots, records, closures, ledger_by_slot)
    implementation_plan = _index_implementation_plan(document["implementation_plan"])
    findings_by_id = {item.id: item for item in sources["findings"]}
    diagnostics: list[dict[str, Any]] = []
    states: dict[str, str] = {}

    states["intent_alignment"] = _evaluate_intent(document, sources, diagnostics)
    states["decision_closure"] = _evaluate_closure(slots, closures, records, diagnostics)
    trace_state, implementation_state = _evaluate_p0_chain(
        slots,
        records,
        ledger_by_slot,
        findings_by_id,
        implementation_plan,
        diagnostics,
    )
    states["traceability"] = trace_state
    states["implementation_readiness"] = implementation_state
    if evidence_resolver is not None and not _strict_findings_are_authoritative(
        sources["findings"],
        sources["decisions"],
        evidence_resolver,
        diagnostics,
        package_target=target,
    ):
        states["decision_closure"] = "fail"
        states["implementation_readiness"] = "fail"
    repository_state, checks = _evaluate_repository_fit(slots, records, sources, roots, diagnostics)
    states["repository_fit"] = repository_state
    states["operational_quality"] = _evaluate_operational(document, slots, tier, diagnostics)
    return diagnostics, checks, states


def _strict_findings_are_authoritative(
    findings: Sequence[ArtifactRevision],
    decisions: Sequence[ArtifactRevision],
    resolver: EvidenceResolver,
    diagnostics: list[dict[str, Any]],
    *,
    package_target: ArtifactRevision,
) -> bool:
    authoritative = True
    package_target_id = package_target.id
    package_target_ref = ArtifactRef(
        package_target.round_id,
        package_target.id,
        package_target.revision,
    )
    evidence_by_finding: dict[ArtifactRef, tuple[ArtifactRef, ...]] = {}
    findings_by_ref: dict[ArtifactRef, ArtifactRevision] = {}
    for finding in findings:
        slot_id = finding.payload.get("decision_slot_id")
        if (
            finding.payload.get("blueprint_target_id") != package_target_id
            or package_target_ref not in finding.parent_refs
        ):
            diagnostics.append(
                _diagnostic(
                    "decision_closure",
                    "fail",
                    f"Finding Pack {finding.id} is not rooted in exact package Blueprint "
                    f"Target {package_target_id!r}@{package_target.revision}.",
                    slot_id=slot_id if isinstance(slot_id, str) else None,
                )
            )
            authoritative = False
            continue
        if finding.payload.get("evidence_mode") != "strict":
            diagnostics.append(
                _diagnostic(
                    "decision_closure",
                    "fail",
                    f"Finding Pack {finding.id} uses non-authoritative legacy evidence.",
                    slot_id=slot_id if isinstance(slot_id, str) else None,
                )
            )
            authoritative = False
            continue
        observations = finding.payload.get("observations")
        if (
            isinstance(observations, (str, bytes))
            or not isinstance(observations, Sequence)
            or not observations
        ):
            diagnostics.append(
                _diagnostic(
                    "decision_closure",
                    "fail",
                    f"Finding Pack {finding.id} has no strict observations.",
                    slot_id=slot_id if isinstance(slot_id, str) else None,
                )
            )
            authoritative = False
            continue
        references: list[ArtifactRef] = []
        for index, observation in enumerate(observations):
            try:
                if not isinstance(observation, Mapping):
                    raise EvidenceValidationError("observation is not a mapping")
                anchor = EvidenceAnchor.from_dict(observation["anchor"])
                if anchor.artifact_ref is None or anchor.artifact_ref not in finding.parent_refs:
                    raise EvidenceValidationError("Finding Pack lacks exact evidence parent lineage")
                resolver.resolve(anchor)
                if anchor.artifact_ref not in references:
                    references.append(anchor.artifact_ref)
            except (KeyError, TypeError, ValueError, EvidenceValidationError) as error:
                diagnostics.append(
                    _diagnostic(
                        "decision_closure",
                        "fail",
                        f"Finding Pack {finding.id} observation {index} is not authoritative: {error}",
                        slot_id=slot_id if isinstance(slot_id, str) else None,
                    )
                )
                authoritative = False
        finding_ref = ArtifactRef(finding.round_id, finding.id, finding.revision)
        evidence_by_finding[finding_ref] = tuple(references)
        findings_by_ref[finding_ref] = finding
    for decision in decisions:
        linked_findings = [
            reference for reference in decision.parent_refs if reference in evidence_by_finding
        ]
        status = decision.payload.get("status")
        slot_id = decision.payload.get("decision_slot_id")
        target_id = decision.payload.get("blueprint_target_id")
        selected_option = decision.payload.get("selected_option")
        if status in {"selected", "conditional"} and (
            target_id != package_target_id or package_target_ref not in decision.parent_refs
        ):
            diagnostics.append(
                _diagnostic(
                    "decision_closure",
                    "fail",
                    f"Decision {decision.id} is not rooted in exact package Blueprint "
                    f"Target {package_target_id!r}@{package_target.revision}.",
                    slot_id=slot_id if isinstance(slot_id, str) else None,
                    decision_id=decision.id,
                )
            )
            authoritative = False
            continue
        if status in {"selected", "conditional"} and not linked_findings:
            diagnostics.append(
                _diagnostic(
                    "decision_closure",
                    "fail",
                    f"Decision {decision.id} lacks a strict Finding Pack parent lineage.",
                    slot_id=slot_id if isinstance(slot_id, str) else None,
                    decision_id=decision.id,
                )
            )
            authoritative = False
            continue
        if status in {"selected", "conditional"}:
            matching_finding = False
            supports_selected_option = False
            for finding_ref in linked_findings:
                finding = findings_by_ref[finding_ref]
                if (
                    not isinstance(target_id, str)
                    or not isinstance(slot_id, str)
                    or finding.payload.get("blueprint_target_id") != target_id
                    or finding.payload.get("decision_slot_id") != slot_id
                ):
                    diagnostics.append(
                        _diagnostic(
                            "decision_closure",
                            "fail",
                            f"Decision {decision.id} and Finding Pack {finding.id} do not share a Blueprint Target and Decision Slot.",
                            slot_id=slot_id if isinstance(slot_id, str) else None,
                            decision_id=decision.id,
                        )
                    )
                    authoritative = False
                    continue
                matching_finding = True
                if isinstance(selected_option, str) and any(
                    isinstance(effect, Mapping)
                    and effect.get("option") == selected_option
                    and effect.get("effect") == "supports"
                    for effect in finding.payload.get("option_effects", ())
                ):
                    supports_selected_option = True
            if not matching_finding or not supports_selected_option:
                diagnostics.append(
                    _diagnostic(
                        "decision_closure",
                        "fail",
                        f"Decision {decision.id} lacks strict Finding Pack support for its selected option.",
                        slot_id=slot_id if isinstance(slot_id, str) else None,
                        decision_id=decision.id,
                    )
                )
                authoritative = False
            candidate_claims = []
            for candidate in findings:
                if (
                    candidate.payload.get("blueprint_target_id") == target_id
                    and candidate.payload.get("decision_slot_id") == slot_id
                ):
                    try:
                        candidate_claims.extend(
                            claim_from_mapping(value) for value in candidate.payload.get("claims", ())
                        )
                    except (TypeError, ValueError) as error:
                        diagnostics.append(
                            _diagnostic(
                                "decision_closure",
                                "fail",
                                f"Finding Pack {candidate.id} has invalid canonical claims: {error}",
                                slot_id=slot_id if isinstance(slot_id, str) else None,
                                decision_id=decision.id,
                            )
                        )
                        authoritative = False
            contested = unresolved_claim_ids(candidate_claims)
            contradiction_artifacts = [
                item
                for item in resolver.ledger.load_run(decision.round_id).artifacts
                if item.kind in {"contradiction-packet", "contradiction-resolution", "contradiction-retraction"}
            ]
            packet_payloads = [
                item.payload for item in contradiction_artifacts if item.kind == "contradiction-packet"
            ]
            resolution_payloads = [
                item.payload for item in contradiction_artifacts if item.kind == "contradiction-resolution"
            ]
            retraction_payloads = [
                item.payload for item in contradiction_artifacts if item.kind == "contradiction-retraction"
            ]
            active_packets = blocking_contradictions(
                packet_payloads, contested, resolution_payloads=resolution_payloads
            )
            packet_detail = "; ".join(
                f"contradiction packet {identifier} claims {','.join(claim_ids)}"
                for identifier, claim_ids in active_packets
            )
            invalidating = invalidating_contradictions(
                retraction_payloads,
                round_id=decision.round_id,
                artifact_id=decision.id,
                revision=decision.revision,
            )
            if invalidating:
                raise InvalidReadinessError(
                    f"Decision {decision.id} was invalidated by {packet_detail or 'contradiction retraction'}; "
                    "create fresh decision lineage from a terminal resolution."
                )
            selected_claim_ids = {
                claim_id
                for finding_ref in linked_findings
                for effect in findings_by_ref[finding_ref].payload.get("option_effects", ())
                if isinstance(effect, Mapping)
                and effect.get("option") == selected_option
                and effect.get("effect") == "supports"
                for claim_id in effect.get("claim_ids", ())
                if isinstance(claim_id, str)
            }
            if contested.intersection(selected_claim_ids):
                detail = packet_detail or "no persisted contradiction packet"
                diagnostics.append(
                    _diagnostic(
                        "decision_closure",
                        "fail",
                        f"Decision {decision.id} relies on an unresolved canonical contradiction: {detail}.",
                        slot_id=slot_id if isinstance(slot_id, str) else None,
                        decision_id=decision.id,
                    )
                )
                authoritative = False
        for finding_ref in linked_findings:
            missing = set(evidence_by_finding[finding_ref]) - set(decision.parent_refs)
            if missing:
                diagnostics.append(
                    _diagnostic(
                        "decision_closure",
                        "fail",
                        f"Decision {decision.id} lacks strict evidence parent lineage from {finding_ref.artifact_id}.",
                        slot_id=slot_id if isinstance(slot_id, str) else None,
                        decision_id=decision.id,
                    )
                )
                authoritative = False
    return authoritative


def _apply_risk_verification(
    assessment: RiskVerificationAssessment,
    artifacts: Sequence[ArtifactRevision],
    *,
    slots: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    diagnostics: list[dict[str, Any]],
    gate_states: dict[str, str],
) -> dict[str, Any]:
    """Attach execution failures to current-round work without changing the target."""

    evidence = thaw_json(assessment.evidence)
    if not isinstance(evidence, dict):
        raise InvalidReadinessError("risk verification assessment must be a JSON object")
    raw_failures = _mappings(evidence.get("failures"), "risk verification failures")
    latest_work = _latest_work_items(artifacts)
    resolved_failures: list[dict[str, Any]] = []
    follow_ups: list[dict[str, Any]] = []
    resolved_by_signature: dict[tuple[str, str], dict[str, Any]] = {}

    for index, raw in enumerate(raw_failures):
        label = f"risk verification failures[{index}]"
        category = _enum(raw.get("category"), f"{label}.category", set(FAILURE_CATEGORY_GATES))
        summary = _nonempty(raw.get("summary"), f"{label}.summary")
        slot_id, work_item_id = _resolve_verification_failure_target(
            raw,
            slots,
            latest_work,
            label,
        )
        decision = records.get(slot_id)
        gate = FAILURE_CATEGORY_GATES[category]
        gate_states[gate] = "fail"
        diagnostics.append(
            _diagnostic(
                gate,
                "fail",
                summary,
                slot_id=slot_id,
                decision_id=None if decision is None else decision.get("decision_id"),
                work_item_id=work_item_id,
                failure_category=category,
            )
        )
        resolved = {
            "category": category,
            "summary": summary,
            "decision_slot_id": slot_id,
            "work_item_id": work_item_id,
        }
        resolved_failures.append(resolved)
        follow_ups.append(
            {
                "category": category,
                "decision_slot_id": slot_id,
                "work_item_id": work_item_id,
                "action": "replan",
                "summary": summary,
            }
        )
        resolved_by_signature[(category, summary)] = resolved

    for check in _mappings(evidence.get("executed_checks"), "risk verification executed checks"):
        failure = check.get("failure")
        if failure is None:
            continue
        raw_failure = _mapping(failure, "risk verification execution failure")
        signature = (
            _nonempty(raw_failure.get("category"), "risk verification execution failure category"),
            _nonempty(raw_failure.get("summary"), "risk verification execution failure summary"),
        )
        resolved = resolved_by_signature.get(signature)
        if resolved is None:
            raise InvalidReadinessError(
                "risk verification executed check failure is absent from its failure list"
            )
        check["failure"] = dict(resolved)

    evidence["failures"] = resolved_failures
    evidence["same_round_follow_ups"] = follow_ups
    return evidence


def _latest_work_items(artifacts: Sequence[ArtifactRevision]) -> dict[str, ArtifactRevision]:
    latest: dict[str, ArtifactRevision] = {}
    for artifact in artifacts:
        if artifact.kind != "work-item":
            continue
        previous = latest.get(artifact.id)
        if previous is None or artifact.revision > previous.revision:
            latest[artifact.id] = artifact
    return latest


def _resolve_verification_failure_target(
    failure: Mapping[str, Any],
    slots: Mapping[str, Mapping[str, Any]],
    latest_work: Mapping[str, ArtifactRevision],
    label: str,
) -> tuple[str, str | None]:
    raw_slot = failure.get("decision_slot_id")
    slot_id = None if raw_slot is None else _identifier(raw_slot, f"{label}.decision_slot_id")
    raw_work = failure.get("work_item_id")
    work_item_id = None if raw_work is None else _identifier(raw_work, f"{label}.work_item_id")
    if work_item_id is not None:
        work = latest_work.get(work_item_id)
        if work is None:
            raise InvalidReadinessError(
                f"{label}.work_item_id must identify a current-round Work Item"
            )
        work_slot = _identifier(work.payload.get("decision_slot_id"), f"Work Item {work.id} decision_slot_id")
        if slot_id is not None and slot_id != work_slot:
            raise InvalidReadinessError(
                f"{label} names a Work Item owned by a different Decision Slot"
            )
        slot_id = work_slot
    if slot_id is None:
        slot_id = next(
            (
                candidate
                for candidate in _stable_slot_order(slots)
                if slots[candidate].get("priority") == "P0"
            ),
            None,
        )
    if slot_id is None:
        slot_id = next(iter(_stable_slot_order(slots)), None)
    if slot_id is None or slot_id not in slots:
        raise InvalidReadinessError(f"{label} cannot be assigned to a current Decision Slot")
    return slot_id, work_item_id


def _index_ledgers(
    decisions: Sequence[ArtifactRevision],
) -> dict[str, ArtifactRevision]:
    indexed: dict[str, ArtifactRevision] = {}
    for ledger in decisions:
        slot_id = _identifier(ledger.payload.get("decision_slot_id"), "ledger decision_slot_id")
        if slot_id in indexed:
            raise InvalidReadinessError(
                f"technical package traces multiple Decision Ledger entries for slot {slot_id}"
            )
        indexed[slot_id] = ledger
    return indexed


def _index_implementation_plan(
    value: Any,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    indexed: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for item in _mappings(value, "implementation_plan"):
        key = (
            _identifier(item.get("decision_slot_id"), "implementation task decision_slot_id"),
            _identifier(item.get("decision_id"), "implementation task decision_id"),
            _identifier(item.get("change_task_id"), "implementation task change_task_id"),
        )
        if key in indexed:
            raise InvalidReadinessError(
                "technical package implementation_plan repeats a decision change task"
            )
        indexed[key] = item
    return indexed


def _ensure_package_decision_lineage(
    slots: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    closures: Mapping[str, Mapping[str, Any]],
    ledger_by_slot: Mapping[str, ArtifactRevision],
) -> None:
    unknown_records = set(records) - set(slots)
    unknown_closures = set(closures) - set(slots)
    if unknown_records or unknown_closures:
        raise InvalidReadinessError(
            "technical package has Decision Slot ids absent from its Blueprint Target: "
            f"records={sorted(unknown_records)}, closures={sorted(unknown_closures)}"
        )
    if set(records) != set(ledger_by_slot):
        raise InvalidReadinessError(
            "technical package decision records and traced Decision Ledger entries differ: "
            f"records={sorted(records)}, ledgers={sorted(ledger_by_slot)}"
        )
    for slot_id, record in records.items():
        ledger = ledger_by_slot[slot_id]
        expected_record = _expected_decision_record(slots[slot_id], ledger)
        if record != expected_record:
            raise InvalidReadinessError(
                f"technical package decision record for slot {slot_id} does not match its exact ledger revision"
            )
    for slot_id in _stable_slot_order(slots):
        expected_closure = _expected_blueprint_closure(
            slot_id,
            slots[slot_id],
            records.get(slot_id),
        )
        if closures.get(slot_id) != expected_closure:
            raise InvalidReadinessError(
                f"technical package closure for slot {slot_id} does not match its exact Decision Ledger and Blueprint Target"
            )


def _expected_decision_record(
    slot: Mapping[str, Any], ledger: ArtifactRevision
) -> dict[str, Any]:
    data = _mapping(ledger.payload, f"Decision Ledger {ledger.id}")
    return {
        "decision_id": ledger.id,
        "revision": ledger.revision,
        "decision_slot_id": data["decision_slot_id"],
        "priority": slot["priority"],
        "kind": slot["kind"],
        "intent_hypothesis_ids": slot["intent_hypothesis_ids"],
        "dependencies": slot["depends_on"],
        "status": data["status"],
        "selected_option": data["selected_option"],
        "alternatives": data["alternatives"],
        "anchors": data["anchors"],
        "design_consequence": data["design_consequence"],
        "repository_touchpoints": data["repository_touchpoints"],
        "validation": data["validation"],
        "change_tasks": data["change_tasks"],
        "assumptions": data["assumptions"],
        "fallback": data["fallback"],
        "reversal_condition": data["reversal_condition"],
    }


def _expected_blueprint_closure(
    slot_id: str,
    slot: Mapping[str, Any],
    record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if record is None:
        return {
            "decision_slot_id": slot_id,
            "priority": slot["priority"],
            "question": slot["question"],
            "intent_hypothesis_ids": slot["intent_hypothesis_ids"],
            "status": "missing",
            "selected_option": None,
            "closure_or_fallback": slot["fallback"],
            "next_action": "Create or converge a Decision Ledger entry for this slot.",
        }
    validation = _mapping(record["validation"], f"Decision Slot {slot_id} validation")
    return {
        "decision_slot_id": slot_id,
        "priority": slot["priority"],
        "question": slot["question"],
        "intent_hypothesis_ids": slot["intent_hypothesis_ids"],
        "status": record["status"],
        "selected_option": record["selected_option"],
        "closure_or_fallback": record["fallback"],
        "next_action": f"Run {validation['kind']} validation: {validation['oracle']}",
    }


def _evaluate_intent(
    document: Mapping[str, Any], sources: Mapping[str, Any], diagnostics: list[dict[str, Any]]
) -> str:
    intent_basis = _mapping(document["intent_basis"], "intent_basis")
    hypotheses = _mappings(intent_basis.get("hypotheses"), "intent hypotheses")
    leading_ids = _strings(
        sources["brief"].payload.get("intent_hypothesis_ids"), "brief hypotheses"
    )
    viable_ids = _strings(
        sources["brief"].payload.get("viable_intent_hypothesis_ids"),
        "brief viable hypotheses",
    )
    brief_ids = set(leading_ids + viable_ids)
    model_hypotheses = {
        _identifier(item.get("id"), "intent model hypothesis id"): item
        for item in _mappings(sources["model"].payload.get("hypotheses"), "intent model hypotheses")
        if item.get("id") in brief_ids
    }
    visible_hypotheses = {
        _identifier(item.get("id"), "intent hypothesis id"): item for item in hypotheses
    }
    exact_model_projection = {
        hypothesis_id: {
            field: model_hypothesis[field]
            for field in (
                "id",
                "interpretation",
                "status",
                "signal_refs",
                "confidence",
                "decision_consequence",
                "validation",
            )
        }
        for hypothesis_id, model_hypothesis in model_hypotheses.items()
    }
    if (
        len(leading_ids) != 1
        or len([item for item in hypotheses if item.get("status") == "leading"]) != 1
        or set(visible_hypotheses) != brief_ids
        or visible_hypotheses != exact_model_projection
        or leading_ids[0] not in visible_hypotheses
        or visible_hypotheses[leading_ids[0]].get("status") != "leading"
    ):
        diagnostics.append(
            _diagnostic(
                "intent_alignment",
                "fail",
                "The package does not expose the Working Brief leading interpretation and material hypotheses.",
            )
        )
        return "fail"
    return "pass"


def _evaluate_closure(
    slots: Mapping[str, Mapping[str, Any]],
    closures: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> str:
    failed = False
    for slot_id in _stable_slot_order(slots):
        closure = closures.get(slot_id)
        record = records.get(slot_id)
        status = None if closure is None else closure.get("status")
        if status in {None, "missing", "blocked"}:
            failed = True
            diagnostics.append(
                _diagnostic(
                    "decision_closure",
                    "fail",
                    f"Decision Slot {slot_id} is {status or 'absent'} and cannot close the blueprint.",
                    slot_id=slot_id,
                    decision_id=None if record is None else record.get("decision_id"),
                )
            )
        elif status == "conditional":
            if record is None or not _has_validation(record):
                failed = True
                diagnostics.append(
                    _diagnostic(
                        "decision_closure",
                        "fail",
                        f"Conditional Decision Slot {slot_id} lacks a concrete validation oracle.",
                        slot_id=slot_id,
                        decision_id=None if record is None else record.get("decision_id"),
                    )
                )
        elif status == "deferred":
            if record is None or not _is_nonempty(record.get("fallback")):
                failed = True
                diagnostics.append(
                    _diagnostic(
                        "decision_closure",
                        "fail",
                        f"Deferred Decision Slot {slot_id} lacks a recorded fallback.",
                        slot_id=slot_id,
                        decision_id=None if record is None else record.get("decision_id"),
                    )
                )
    if failed:
        return "fail"
    return "pass"


def _evaluate_p0_chain(
    slots: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    ledger_by_slot: Mapping[str, ArtifactRevision],
    findings_by_id: Mapping[str, ArtifactRevision],
    implementation_plan: Mapping[tuple[str, str, str], Mapping[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> tuple[str, str]:
    trace_failed = False
    implementation_failed = False
    for slot_id in _stable_slot_order(slots):
        slot = slots[slot_id]
        if slot.get("priority") != "P0":
            continue
        record = records.get(slot_id)
        ledger = ledger_by_slot.get(slot_id)
        if record is None or ledger is None:
            trace_failed = True
            implementation_failed = True
            diagnostics.extend(
                (
                    _diagnostic(
                        "traceability",
                        "fail",
                        f"P0 Decision Slot {slot_id} lacks an exact Decision Ledger record.",
                        slot_id=slot_id,
                    ),
                    _diagnostic(
                        "implementation_readiness",
                        "fail",
                        f"P0 Decision Slot {slot_id} has no design consequence, change task, or acceptance oracle.",
                        slot_id=slot_id,
                    ),
                )
            )
            continue
        status = record.get("status")
        if status == "blocked":
            implementation_failed = True
            diagnostics.append(
                _diagnostic(
                    "implementation_readiness",
                    "fail",
                    f"P0 Decision Slot {slot_id} is blocked.",
                    slot_id=slot_id,
                    decision_id=ledger.id,
                )
            )
            continue
        anchors = _mappings(record.get("anchors"), f"P0 {slot_id} anchors")
        finding_ids = {
            _identifier(anchor.get("ref"), "finding anchor ref")
            for anchor in anchors
            if anchor.get("kind") == "finding" and _is_nonempty(anchor.get("ref"))
        }
        linked_finding_ids = {
            ref.artifact_id for ref in ledger.parent_refs if ref.artifact_id in findings_by_id
        }
        selected = record.get("selected_option")
        selected_effect = any(
            selected in {
                effect.get("option")
                for effect in _mappings(finding.payload.get("option_effects"), "finding option_effects")
            }
            for finding_id, finding in findings_by_id.items()
            if finding_id in linked_finding_ids
        )
        if not anchors or not finding_ids <= linked_finding_ids or (selected is not None and not selected_effect):
            trace_failed = True
            diagnostics.append(
                _diagnostic(
                    "traceability",
                    "fail",
                    f"P0 Decision Slot {slot_id} lacks a linked Finding Pack anchor for its selected option.",
                    slot_id=slot_id,
                    decision_id=ledger.id,
                )
            )
        has_touchpoint = bool(_mappings(record.get("repository_touchpoints"), "repository_touchpoints"))
        greenfield = bool(_strings(slot.get("greenfield_assumptions"), "greenfield_assumptions"))
        tasks = _mappings(record.get("change_tasks"), "change_tasks")
        task_valid = bool(tasks) and all(
            _is_nonempty(task.get("description")) and _is_nonempty(task.get("acceptance_oracle"))
            for task in tasks
        )
        expected_plan_keys = {
            (slot_id, ledger.id, _identifier(task.get("id"), "change task id"))
            for task in tasks
        }
        actual_plan_keys = {
            key for key in implementation_plan if key[:2] == (slot_id, ledger.id)
        }
        plan_valid = expected_plan_keys == actual_plan_keys and all(
            _plan_item_matches_task(
                implementation_plan[key],
                task,
                record,
            )
            for task in tasks
            for key in expected_plan_keys
            if key[2] == task.get("id")
        )
        if status in {"selected", "conditional"} and (
            not _is_nonempty(record.get("design_consequence"))
            or not has_touchpoint and not greenfield
            or not task_valid
            or not _has_validation(record)
            or not plan_valid
        ):
            implementation_failed = True
            diagnostics.append(
                _diagnostic(
                    "implementation_readiness",
                    "fail",
                    f"P0 Decision Slot {slot_id} lacks an actionable ordered implementation plan, change task, acceptance oracle, or validation.",
                    slot_id=slot_id,
                    decision_id=ledger.id,
                )
            )
        elif status == "deferred":
            if not _is_nonempty(record.get("fallback")):
                implementation_failed = True
                diagnostics.append(
                    _diagnostic(
                        "implementation_readiness",
                        "fail",
                        f"Deferred P0 Decision Slot {slot_id} lacks a fallback.",
                        slot_id=slot_id,
                        decision_id=ledger.id,
                    )
                )
    return (
        "fail" if trace_failed else "pass",
        "fail" if implementation_failed else "pass",
    )


def _plan_item_matches_task(
    plan_item: Mapping[str, Any],
    task: Mapping[str, Any],
    record: Mapping[str, Any],
) -> bool:
    return (
        plan_item.get("description") == task.get("description")
        and plan_item.get("repository_touchpoints") == task.get("repository_touchpoints")
        and plan_item.get("depends_on") == record.get("dependencies")
        and plan_item.get("validation") == record.get("validation")
        and plan_item.get("rollback") == record.get("fallback")
    )


def _evaluate_repository_fit(
    slots: Mapping[str, Mapping[str, Any]],
    records: Mapping[str, Mapping[str, Any]],
    sources: Mapping[str, Any],
    roots: Mapping[str, Path],
    diagnostics: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    repositories = sources["repositories"]
    if not repositories:
        return "not_applicable", []
    checks: list[dict[str, Any]] = []
    failed = False
    for slot_id in _stable_slot_order(slots):
        slot = slots[slot_id]
        if slot.get("priority") != "P0":
            continue
        record = records.get(slot_id)
        if record is None:
            continue
        for point in _mappings(record.get("repository_touchpoints"), "repository_touchpoints"):
            path = _nonempty(point.get("path"), "repository touchpoint path")
            symbol = point.get("symbol")
            if symbol is not None:
                symbol = _nonempty(symbol, "repository touchpoint symbol")
            candidates = _repositories_for_touchpoint(repositories, path, symbol)
            if not candidates:
                raise InvalidReadinessError(
                    f"Repository touchpoint {path} is absent from every observed repository baseline"
                )
            for repository in candidates:
                input_id = repository.id
                resolved, reason = _resolve_touchpoint(roots[input_id], path, symbol)
                checks.append(
                    {
                        "input_id": input_id,
                        "path": path,
                        "symbol": symbol,
                        "resolved": resolved,
                        "reason": reason,
                    }
                )
                if not resolved:
                    failed = True
                    diagnostics.append(
                        _diagnostic(
                            "repository_fit",
                            "fail",
                            f"Repository touchpoint {path} in {input_id} could not be resolved: {reason}",
                            slot_id=slot_id,
                            decision_id=record.get("decision_id"),
                        )
                    )
    p0_slots = [slot for slot in slots.values() if slot.get("priority") == "P0"]
    if not checks and p0_slots and all(
        _strings(slot.get("greenfield_assumptions"), "greenfield_assumptions")
        for slot in p0_slots
    ):
        return "not_applicable", checks
    return ("fail" if failed else "pass"), checks


def _repositories_for_touchpoint(
    repositories: Sequence[ArtifactRevision],
    path: str,
    symbol: str | None,
) -> tuple[ArtifactRevision, ...]:
    candidates: list[ArtifactRevision] = []
    for repository in sorted(repositories, key=lambda item: item.id):
        baseline = _mapping(
            repository.payload.get("repository_baseline"),
            f"repository baseline for {repository.id}",
        )
        anchors = _mappings(baseline.get("anchors"), f"repository baseline anchors for {repository.id}")
        for anchor in anchors:
            if anchor.get("path") != path:
                continue
            if symbol is None or anchor.get("symbol") == symbol:
                candidates.append(repository)
                break
    return tuple(candidates)


def _evaluate_operational(
    document: Mapping[str, Any],
    slots: Mapping[str, Mapping[str, Any]],
    tier: str,
    diagnostics: list[dict[str, Any]],
) -> str:
    handoff = _mapping(document.get("operational_handoff"), "operational_handoff")
    observability = _mapping(handoff.get("observability"), "operational_handoff.observability")
    rollout = _mapping(handoff.get("rollout"), "operational_handoff.rollout")
    rollback = _mappings(handoff.get("rollback"), "operational_handoff.rollback")
    implementation_plan = _mappings(document.get("implementation_plan"), "implementation_plan")
    rollout_items = _mappings(rollout.get("items"), "operational_handoff.rollout.items")
    expected_tasks = {
        (item.get("decision_slot_id"), item.get("change_task_id")): item
        for item in implementation_plan
    }
    actual_rollouts = {
        (item.get("decision_slot_id"), item.get("change_task_id")): item
        for item in rollout_items
    }
    actual_rollbacks = {
        (item.get("decision_slot_id"), item.get("change_task_id")): item
        for item in rollback
    }
    expected_rollout_status = (
        "derived_from_ordered_change_tasks" if expected_tasks else "unknown"
    )
    rollout_complete = (
        rollout.get("status") == expected_rollout_status
        and len(actual_rollouts) == len(rollout_items)
        and expected_tasks.keys() == actual_rollouts.keys()
        and all(
            actual_rollouts[key].get("order") == expected_tasks[key].get("order")
            and actual_rollouts[key].get("description") == expected_tasks[key].get("description")
            and actual_rollouts[key].get("validation") == expected_tasks[key].get("validation")
            and actual_rollouts[key].get("repository_touchpoints")
            == expected_tasks[key].get("repository_touchpoints")
            for key in expected_tasks
        )
    )
    rollback_complete = (
        len(actual_rollbacks) == len(rollback)
        and expected_tasks.keys() == actual_rollbacks.keys()
        and all(
            actual_rollbacks[key].get("order") == expected_tasks[key].get("order")
            and actual_rollbacks[key].get("fallback") == expected_tasks[key].get("rollback")
            and actual_rollbacks[key].get("validation") == expected_tasks[key].get("validation")
            for key in expected_tasks
        )
    )
    unknown = (
        observability.get("status") in {"missing", "unknown", "blocked"}
        or not rollout_complete
        or not rollback_complete
    )
    if not unknown:
        return "pass"
    item = next(iter(_mappings(observability.get("items"), "observability items")), None)
    slot_id = None if item is None else item.get("decision_slot_id")
    if slot_id is None:
        item = next(iter(_mappings(rollout.get("items"), "rollout items")), None)
        slot_id = None if item is None else item.get("decision_slot_id")
    if slot_id is None:
        item = next(iter(rollback), None)
        slot_id = None if item is None else item.get("decision_slot_id")
    if slot_id is None:
        slot_id = next((key for key in _stable_slot_order(slots) if slots[key].get("kind") == "operations"), None)
    if slot_id is None:
        slot_id = next((key for key in _stable_slot_order(slots) if slots[key].get("priority") == "P0"), None)
    if slot_id is None:
        slot_id = next(iter(_stable_slot_order(slots)), None)
    status = "fail" if tier == "high" else "deferred"
    diagnostics.append(
        _diagnostic(
            "operational_quality",
            status,
            "Operational handoff leaves rollout, rollback, or observability unresolved for this risk tier.",
            slot_id=slot_id,
        )
    )
    return status


def _delivery_projection(
    tier: str, gates: Mapping[str, str], diagnostics: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    findings = [
        {"gate": item["gate"], "summary": item["summary"]}
        for item in diagnostics
    ]
    ids: list[str] = []
    for item in diagnostics:
        recommended = item["recommended_work"]
        if recommended is not None and recommended["id"] not in ids:
            ids.append(recommended["id"])
    return {
        "risk_tier": tier,
        "gates": {gate: gates[gate] for gate in READINESS_GATES},
        "findings": findings,
        "next_work_item_ids": ids,
    }


def _diagnostic(
    gate: str,
    status: str,
    summary: str,
    *,
    slot_id: str | None = None,
    decision_id: str | None = None,
    work_item_id: str | None = None,
    failure_category: str | None = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "status": status,
        "summary": summary,
        "decision_slot_id": slot_id,
        "decision_id": decision_id,
        "work_item_id": work_item_id,
        "recommended_work": (
            None
            if status != "fail" or slot_id is None
            else {
                "id": _recommendation_id(gate, slot_id),
                "decision_slot_id": slot_id,
                "kind": _recommended_kind(gate),
                "scope": summary,
                "reason": f"Resolve the {gate} gate without changing the requester target.",
            }
        ),
        "failure_category": failure_category,
    }


def _recommended_kind(gate: str) -> str:
    return {
        "repository_fit": "repository_analysis",
        "operational_quality": "prototype",
        "implementation_readiness": "prototype",
    }.get(gate, "evaluation")


def _recommendation_id(gate: str, slot_id: str) -> str:
    candidate = f"ready-{gate.replace('_', '-')}-{slot_id}"
    if len(candidate) <= 64:
        return candidate
    digest = sha256(candidate.encode("utf-8")).hexdigest()[:16]
    return f"ready-{gate[:12].replace('_', '-')}-{digest}"


def _resolve_touchpoint(root: Path, path: str, symbol: str | None) -> tuple[bool, str]:
    candidate = (root / path).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return False, "path escapes the supplied repository root"
    if not candidate.is_file():
        return False, "file is absent"
    if symbol is None:
        return True, "path exists"
    try:
        if candidate.stat().st_size > MAX_SYMBOL_CHECK_BYTES:
            return False, "file exceeds the bounded symbol-check size"
        content = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return False, f"file is unreadable: {error.__class__.__name__}"
    if candidate.suffix.lower() != ".py":
        return False, "symbol anchors are only supported for Python source files"
    try:
        module = ast.parse(content, filename=str(candidate))
    except (SyntaxError, ValueError):
        return False, "Python source cannot be parsed"
    definitions = {
        node.name
        for node in module.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if symbol not in definitions:
        return False, f"top-level Python symbol {symbol!r} is absent"
    return True, "path and top-level Python symbol resolve"


def _has_validation(record: Mapping[str, Any]) -> bool:
    validation = record.get("validation")
    return isinstance(validation, Mapping) and _is_nonempty(validation.get("oracle"))


def _ensure_id_compatibility(artifacts: Sequence[ArtifactRevision], artifact_id: str) -> None:
    kinds = {item.kind for item in artifacts if item.id == artifact_id and item.kind != READINESS_RECORD_KIND}
    if kinds:
        raise InvalidReadinessError(
            f"readiness_id {artifact_id!r} is already used by kinds: {sorted(kinds)}"
        )


def _resolve_exact(
    artifacts: Sequence[ArtifactRevision],
    value: ArtifactRevision,
    expected_kind: str,
    label: str,
) -> ArtifactRevision:
    if not isinstance(value, ArtifactRevision):
        raise InvalidReadinessError(f"{label} must be an ArtifactRevision")
    for item in artifacts:
        if item.id == value.id and item.revision == value.revision:
            if item != value:
                raise InvalidReadinessError(f"{label} does not match its stored revision")
            if item.kind != expected_kind:
                raise InvalidReadinessError(f"{label} must be a {expected_kind}")
            return item
    raise InvalidReadinessError(f"{label} has not been persisted in this RunLedger")


def _slots(target: ArtifactRevision) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(_mappings(target.payload.get("slots"), "Blueprint Target slots")):
        slot_id = _identifier(item.get("id"), f"Blueprint Target slots[{index}].id")
        if slot_id in result:
            raise InvalidReadinessError(f"Blueprint Target repeats Decision Slot {slot_id}")
        result[slot_id] = item
    return result


def _stable_slot_order(slots: Mapping[str, Mapping[str, Any]]) -> list[str]:
    remaining = {
        slot_id: set(_identifiers(slot.get("depends_on"), f"slot {slot_id}.depends_on"))
        for slot_id, slot in slots.items()
    }
    for slot_id, dependencies in remaining.items():
        unknown = dependencies - set(remaining)
        if unknown:
            raise InvalidReadinessError(f"slot {slot_id} depends on unknown slots: {sorted(unknown)}")
    ordered: list[str] = []
    while remaining:
        ready = sorted(slot_id for slot_id, dependencies in remaining.items() if not dependencies)
        if not ready:
            raise InvalidReadinessError("Blueprint Target Decision Slot dependencies contain a cycle")
        ordered.extend(ready)
        for slot_id in ready:
            remaining.pop(slot_id)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return ordered


def _validate_recommended_work(value: Any, label: str) -> None:
    if value is None:
        return
    item = _mapping(value, label)
    _require_exact_keys(item, {"id", "decision_slot_id", "kind", "scope", "reason"}, label)
    _identifier(item["id"], f"{label}.id")
    _identifier(item["decision_slot_id"], f"{label}.decision_slot_id")
    _enum(item["kind"], f"{label}.kind", {"repository_analysis", "prototype", "evaluation"})
    _nonempty(item["scope"], f"{label}.scope")
    _nonempty(item["reason"], f"{label}.reason")


def _artifact_ref(value: Any, label: str) -> ArtifactRef:
    data = _mapping(value, label)
    _require_exact_keys(data, {"round_id", "artifact_id", "revision"}, label)
    return ArtifactRef(
        _identifier(data["round_id"], f"{label}.round_id"),
        _identifier(data["artifact_id"], f"{label}.artifact_id"),
        _positive_int(data["revision"], f"{label}.revision"),
    )


def _validate_ref(value: Any, label: str) -> None:
    _artifact_ref(value, label)


def _ref_dict(artifact: ArtifactRevision) -> dict[str, Any]:
    return ArtifactRef(artifact.round_id, artifact.id, artifact.revision).to_dict()


def _unique_refs(values: Sequence[ArtifactRef]) -> tuple[ArtifactRef, ...]:
    result: list[ArtifactRef] = []
    seen: set[tuple[str, str, int]] = set()
    for value in values:
        key = (value.round_id, value.artifact_id, value.revision)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _mappings(value: Any, label: str) -> list[Mapping[str, Any]]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidReadinessError(f"{label} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(plain):
        if not isinstance(item, Mapping):
            raise InvalidReadinessError(f"{label}[{index}] must be a mapping")
        result.append(item)
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    plain = thaw_json(value)
    if not isinstance(plain, Mapping):
        raise InvalidReadinessError(f"{label} must be a mapping")
    return plain


def _strings(value: Any, label: str) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidReadinessError(f"{label} must be a sequence of strings")
    return tuple(_nonempty(item, label) for item in plain)


def _identifiers(value: Any, label: str) -> tuple[str, ...]:
    plain = thaw_json(value)
    if isinstance(plain, (str, bytes)) or not isinstance(plain, Sequence):
        raise InvalidReadinessError(f"{label} must be a sequence of identifiers")
    result = tuple(_identifier(item, label) for item in plain)
    if len(set(result)) != len(result):
        raise InvalidReadinessError(f"{label} must not contain duplicate identifiers")
    return result


def _identifier(value: Any, label: str) -> str:
    try:
        return validate_identifier(value, label)
    except InvalidIdentifierError as error:
        raise InvalidReadinessError(str(error)) from error


def _enum(value: Any, label: str, allowed: set[str]) -> str:
    result = _nonempty(value, label)
    if result not in allowed:
        raise InvalidReadinessError(f"{label} is unsupported: {result}")
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidReadinessError(f"{label} must be a nonempty string")
    return value


def _is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidReadinessError(f"{label} must be a positive integer")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise InvalidReadinessError(
            f"{label} has unexpected keys; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
