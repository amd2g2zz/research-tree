"""Canonical contradiction classification for grounded research claims."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
import re
from typing import Any, Iterable, Mapping, Sequence

from .claims import Claim


class ClaimBoundary(StrEnum):
    ADMISSION = "admission"
    RECALL = "recall"
    REVISION = "revision"
    EXPERIMENT = "experiment"
    FEEDBACK = "feedback"


CLAIM_BOUNDARIES = frozenset(ClaimBoundary)
SCOPE_DIMENSIONS = ("scope", "version", "time_range", "platform", "condition_mode", "conditions", "modality")


class ContradictionStatus(StrEnum):
    CANDIDATE_CONFLICT = "candidate-conflict"
    SCOPE_SEPARATED = "scope-separated"
    CONTESTED = "contested"
    RESOLVED_A = "resolved-a"
    RESOLVED_B = "resolved-b"
    BOTH_LIMITED = "both-limited"
    SUPERSEDED = "superseded"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ScopeDimensionResult:
    dimension: str
    overlap: bool
    left: str
    right: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "overlap": self.overlap,
            "left": self.left,
            "right": self.right,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class ContradictionPacket:
    claim_ids: tuple[str, ...]
    status: ContradictionStatus
    reason: str
    conflicting_values: tuple[str, ...] = ()
    unresolved_dimensions: tuple[str, ...] = ()
    scope_dimensions: tuple[ScopeDimensionResult, ...] = ()
    normalized_claims: tuple[dict[str, Any], ...] = ()
    boundary: ClaimBoundary = ClaimBoundary.ADMISSION

    def __post_init__(self) -> None:
        if (
            len(self.claim_ids) < 2
            or self.claim_ids != tuple(sorted(self.claim_ids))
            or len(set(self.claim_ids)) != len(self.claim_ids)
        ):
            raise ValueError("contradiction packet claim_ids must be distinct and sorted")

    @property
    def decision_authority(self) -> bool:
        return self.status not in {ContradictionStatus.UNRESOLVED, ContradictionStatus.CONTESTED}


def _artifact_ref_key(value: Mapping[str, Any]) -> tuple[str, str, int] | None:
    round_id = value.get("round_id")
    artifact_id = value.get("artifact_id")
    revision = value.get("revision")
    if not isinstance(round_id, str) or not isinstance(artifact_id, str):
        return None
    if isinstance(revision, bool) or not isinstance(revision, int):
        return None
    return round_id, artifact_id, revision


def _terminal_authorized_claim_ids(
    packet: Mapping[str, Any], resolution_payloads: Sequence[Mapping[str, Any]]
) -> frozenset[str] | None:
    """Return claim authority conferred by one valid terminal resolution chain."""

    round_id = packet.get("run_id")
    packet_id = packet.get("contradiction_id")
    if not isinstance(round_id, str) or not isinstance(packet_id, str):
        return None
    packet_ref = (round_id, packet_id, 1)
    resolutions = [
        payload for payload in resolution_payloads if _artifact_ref_key(payload.get("packet_ref", {})) == packet_ref
    ]
    if not resolutions:
        return None
    by_id: dict[str, Mapping[str, Any]] = {}
    for payload in resolutions:
        resolution_id = payload.get("resolution_id")
        if not isinstance(resolution_id, str) or resolution_id in by_id:
            return None
        by_id[resolution_id] = payload

    prior_ids = {
        identifier
        for payload in resolutions
        if isinstance(payload.get("prior_resolution_ref"), Mapping)
        and isinstance((identifier := payload["prior_resolution_ref"].get("artifact_id")), str)
    }
    roots = [payload for payload in resolutions if payload.get("prior_resolution_ref") is None]
    terminals = [payload for payload in resolutions if payload["resolution_id"] not in prior_ids]
    if len(roots) != 1 or len(terminals) != 1 or roots[0]["resolution_id"] not in by_id:
        return None

    chain: list[Mapping[str, Any]] = []
    current: Mapping[str, Any] | None = terminals[0]
    while current is not None:
        if current["resolution_id"] in {payload["resolution_id"] for payload in chain}:
            return None
        chain.append(current)
        prior = current.get("prior_resolution_ref")
        if prior is None:
            break
        if not isinstance(prior, Mapping):
            return None
        prior_id = prior.get("artifact_id")
        if not isinstance(prior_id, str):
            return None
        current = by_id.get(prior_id)
    if {payload["resolution_id"] for payload in chain} != set(by_id):
        return None

    terminal = terminals[0]
    transition = terminal.get("transition")
    if transition == "superseded":
        return frozenset()
    selected = terminal.get("selected_claim_ids", ())
    if isinstance(selected, (str, bytes)) or not isinstance(selected, Sequence):
        return None
    selected_ids = frozenset(str(value) for value in selected)
    participating = frozenset(str(value) for value in packet.get("claim_ids", ()))
    if not selected_ids <= participating:
        return None
    if transition == "both-limited":
        return frozenset() if not selected_ids else None
    if transition not in {"resolved-a", "resolved-b"}:
        return None
    return selected_ids if selected_ids and selected_ids != participating else None


def _semantic_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalized_version(value: str) -> str:
    normalized = _semantic_text(value)
    return normalized[1:] if normalized.startswith("v") else normalized


def _normalized_condition(value: str) -> str:
    return _semantic_text(value)


def _time_bounds(value: str) -> tuple[str, str] | None:
    normalized = value.strip().casefold().replace(" ", "")
    for separator in ("..", "to"):
        if separator in normalized:
            left, right = normalized.split(separator, 1)
            return (_semantic_text(left), _semantic_text(right)) if left and right else None
    normalized = _semantic_text(normalized)
    return normalized, normalized


def _time_overlaps(left: str, right: str) -> bool | None:
    left_bounds = _time_bounds(left)
    right_bounds = _time_bounds(right)
    if left_bounds is None or right_bounds is None:
        return None
    return max(left_bounds[0], right_bounds[0]) <= min(left_bounds[1], right_bounds[1])


def _condition_mode(values: tuple[str, ...]) -> str:
    normalized = {_normalized_condition(value) for value in values}
    if "default" in normalized:
        return "default"
    return "optional" if normalized else "unspecified"


def _scope_results(left: Claim, right: Claim) -> tuple[ScopeDimensionResult, ...]:
    values = {
        "scope": (_semantic_text(left.scope), _semantic_text(right.scope)),
        "version": (_normalized_version(left.version), _normalized_version(right.version)),
        "time_range": (_semantic_text(left.time_range), _semantic_text(right.time_range)),
        "platform": (_semantic_text(left.platform), _semantic_text(right.platform)),
        "modality": (_semantic_text(left.modality), _semantic_text(right.modality)),
    }
    results = [
        ScopeDimensionResult(name, left_value == right_value, left_value, right_value, f"{name}: separated")
        if left_value != right_value
        else ScopeDimensionResult(name, True, left_value, right_value, f"{name}: overlap")
        for name, (left_value, right_value) in values.items()
    ]
    time_overlap = _time_overlaps(left.time_range, right.time_range)
    if time_overlap is not None:
        results = [result for result in results if result.dimension != "time_range"]
        results.append(
            ScopeDimensionResult(
                "time_range",
                time_overlap,
                values["time_range"][0],
                values["time_range"][1],
                "time_range: overlap" if time_overlap else "time_range: separated",
            )
        )

    left_conditions = tuple(sorted({_normalized_condition(value) for value in left.conditions}))
    right_conditions = tuple(sorted({_normalized_condition(value) for value in right.conditions}))
    left_mode = _condition_mode(left.conditions)
    right_mode = _condition_mode(right.conditions)
    mode_overlaps = left_mode == right_mode
    results.append(
        ScopeDimensionResult(
            "condition_mode",
            mode_overlaps,
            left_mode,
            right_mode,
            "condition_mode: overlap" if mode_overlaps else "condition_mode: separated",
        )
    )
    condition_overlap = bool(set(left_conditions) & set(right_conditions))
    conditions_compatible = left_conditions == right_conditions or (condition_overlap and left_mode == right_mode)
    results.append(
        ScopeDimensionResult(
            "conditions",
            conditions_compatible,
            ",".join(left_conditions),
            ",".join(right_conditions),
            "conditions: overlap" if conditions_compatible else "conditions: separated",
        )
    )
    return tuple(result for result in results if result.dimension in SCOPE_DIMENSIONS)


def _normalized_claim(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "subject": _semantic_text(claim.subject),
        "predicate": _semantic_text(claim.predicate),
        "value": claim.value,
        "polarity": claim.polarity,
        "scope": _semantic_text(claim.scope),
        "version": _normalized_version(claim.version),
        "time_range": _semantic_text(claim.time_range),
        "platform": _semantic_text(claim.platform),
        "modality": _semantic_text(claim.modality),
        "conditions": sorted({_normalized_condition(value) for value in claim.conditions}),
    }


def _conflicts(left: Claim, right: Claim) -> bool:
    if left.polarity != right.polarity:
        return True
    left_interval = _numeric_interval(left.value)
    right_interval = _numeric_interval(right.value)
    if left_interval is not None and right_interval is not None:
        return left_interval[1] < right_interval[0] or right_interval[1] < left_interval[0]
    return left.value.casefold() != right.value.casefold()


def _numeric_interval(value: str) -> tuple[float, float] | None:
    normalized = value.strip().replace(" ", "")
    bounded = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)", normalized)
    if bounded:
        lower, upper = (float(item) for item in bounded.groups())
        return (lower, upper) if lower <= upper else None
    lower_bounded = re.fullmatch(r">=(-?\d+(?:\.\d+)?)", normalized)
    if lower_bounded:
        return (float(lower_bounded.group(1)), float("inf"))
    upper_bounded = re.fullmatch(r"<=(-?\d+(?:\.\d+)?)", normalized)
    if upper_bounded:
        return (float("-inf"), float(upper_bounded.group(1)))
    scalar = re.fullmatch(r"-?\d+(?:\.\d+)?", normalized)
    if scalar:
        number = float(normalized)
        return number, number
    return None


class ContradictionDetector:
    """The only claim-comparison implementation used at canonical boundaries."""

    def detect(
        self,
        claims: Iterable[Claim],
        *,
        boundary: ClaimBoundary | str = ClaimBoundary.ADMISSION,
        claim_refs: Mapping[str, Any] | None = None,
    ) -> tuple[ContradictionPacket, ...]:
        del claim_refs
        typed_boundary = ClaimBoundary(boundary)
        values = tuple(claims)
        if any(not isinstance(claim, Claim) for claim in values):
            raise ValueError("claims must contain Claim values")
        by_id = {claim.claim_id: claim for claim in values}
        if len(by_id) != len(values):
            raise ValueError("claims must contain distinct claim_id values")

        parent = {claim.claim_id: claim.claim_id for claim in values}

        def root(claim_id: str) -> str:
            while parent[claim_id] != claim_id:
                parent[claim_id] = parent[parent[claim_id]]
                claim_id = parent[claim_id]
            return claim_id

        def union(left: str, right: str) -> None:
            left_root, right_root = root(left), root(right)
            if left_root != right_root:
                parent[max(left_root, right_root)] = min(left_root, right_root)

        separated: list[ContradictionPacket] = []
        for left, right in combinations(sorted(values, key=lambda claim: claim.claim_id), 2):
            if (
                _semantic_text(left.subject) != _semantic_text(right.subject)
                or _semantic_text(left.predicate) != _semantic_text(right.predicate)
                or not _conflicts(left, right)
            ):
                continue
            dimensions = _scope_results(left, right)
            if any(not result.overlap for result in dimensions):
                separating = tuple(result.dimension for result in dimensions if not result.overlap)
                separated.append(
                    ContradictionPacket(
                        tuple(sorted((left.claim_id, right.claim_id))),
                        ContradictionStatus.SCOPE_SEPARATED,
                        "non-overlapping-applicability:" + ",".join(separating),
                        tuple(sorted((left.value, right.value))),
                        (),
                        dimensions,
                        (_normalized_claim(left), _normalized_claim(right)),
                        typed_boundary,
                    )
                )
                continue
            union(left.claim_id, right.claim_id)

        packets = list(separated)
        groups: dict[str, list[Claim]] = {}
        for claim in values:
            groups.setdefault(root(claim.claim_id), []).append(claim)
        for group in groups.values():
            if len(group) < 2:
                continue
            claims = sorted(group, key=lambda claim: claim.claim_id)
            dimensions_by_pair = [_scope_results(left, right) for left, right in combinations(claims, 2)]
            unresolved = {
                result.dimension
                for pair in dimensions_by_pair
                for result in pair
                if result.overlap and result.left != result.right
            }
            if any(left.polarity != right.polarity for left, right in combinations(claims, 2)):
                unresolved.add("polarity")
            if len({left.value for left in claims}) > 1:
                unresolved.add("value")
            packets.append(
                ContradictionPacket(
                    tuple(claim.claim_id for claim in claims),
                    ContradictionStatus.CONTESTED,
                    "incompatible-applicable-claims",
                    tuple(sorted({claim.value for claim in claims})),
                    tuple(sorted(unresolved)),
                    tuple(result for pair in dimensions_by_pair for result in pair),
                    tuple(_normalized_claim(by_id[claim.claim_id]) for claim in claims),
                    typed_boundary,
                )
            )
        return tuple(sorted(packets, key=lambda packet: packet.claim_ids))


def detect_contradictions(
    claims: Iterable[Claim],
    *,
    boundary: ClaimBoundary | str = ClaimBoundary.ADMISSION,
    claim_refs: Mapping[str, Any] | None = None,
) -> tuple[ContradictionPacket, ...]:
    return ContradictionDetector().detect(claims, boundary=boundary, claim_refs=claim_refs)


def derive_contradiction_packets(claims: Iterable[Claim]) -> tuple[ContradictionPacket, ...]:
    """Derive deterministic conflicts without trusting worker option effects."""

    return detect_contradictions(claims, boundary=ClaimBoundary.ADMISSION)


def claim_from_mapping(value: Mapping[str, Any]) -> Claim:
    """Decode current and pre-platform canonical claim payloads."""

    required = {
        "claim_id",
        "subject",
        "predicate",
        "value",
        "polarity",
        "scope",
        "version",
        "time_range",
        "conditions",
    }
    optional = {"platform", "modality"}
    if set(value) - required - optional or not required <= set(value):
        raise ValueError("claim has unsupported fields")
    conditions = value["conditions"]
    if isinstance(conditions, (str, bytes)) or not isinstance(conditions, Sequence):
        raise ValueError("claim conditions must be a sequence")
    return Claim(
        claim_id=value["claim_id"],
        subject=value["subject"],
        predicate=value["predicate"],
        value=value["value"],
        polarity=value["polarity"],
        scope=value["scope"],
        version=value["version"],
        time_range=value["time_range"],
        conditions=tuple(conditions),
        platform=value.get("platform", "unspecified"),
        modality=value.get("modality", "unspecified"),
    )


def unresolved_claim_ids(claims: Iterable[Claim]) -> frozenset[str]:
    """Return claims that cannot currently confer decision authority."""

    return frozenset(
        claim_id
        for packet in derive_contradiction_packets(claims)
        if packet.status in {ContradictionStatus.UNRESOLVED, ContradictionStatus.CONTESTED}
        for claim_id in packet.claim_ids
    )


def blocking_contradictions(
    packet_payloads: Iterable[Mapping[str, Any]],
    claim_ids: Iterable[str],
    *,
    resolution_payloads: Iterable[Mapping[str, Any]] = (),
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return active packet authority conflicts for the supplied claim set."""

    requested = set(claim_ids)
    resolutions = tuple(resolution_payloads)
    result: list[tuple[str, tuple[str, ...]]] = []
    for payload in packet_payloads:
        if payload.get("status") not in {ContradictionStatus.CONTESTED.value, ContradictionStatus.UNRESOLVED.value}:
            continue
        participating_tuple = tuple(str(value) for value in payload.get("claim_ids", ()))
        participating = frozenset(participating_tuple)
        authorized = _terminal_authorized_claim_ids(payload, resolutions)
        blocked = participating if authorized is None else participating - authorized
        if requested.intersection(blocked):
            identifier = str(payload.get("contradiction_id", ""))
            if identifier:
                result.append((identifier, participating_tuple))
    return tuple(sorted(result))


def invalidating_contradictions(
    retraction_payloads: Iterable[Mapping[str, Any]],
    *,
    round_id: str,
    artifact_id: str,
    revision: int,
) -> tuple[str, ...]:
    """Return contradiction IDs whose retraction invalidates this exact revision."""

    identifiers = []
    for payload in retraction_payloads:
        for raw_ref in payload.get("invalidated_refs", ()):
            if not isinstance(raw_ref, Mapping):
                continue
            if _artifact_ref_key(raw_ref) == (round_id, artifact_id, revision):
                identifier = payload.get("contradiction_id")
                if isinstance(identifier, str):
                    identifiers.append(identifier)
    return tuple(sorted(set(identifiers)))


def render_contradiction_packet(packet: Mapping[str, Any]) -> str:
    """Render packet provenance and consequences without mutable run state."""

    identifier = str(packet.get("contradiction_id", "contradiction-unidentified"))
    lines = [f"# Contradiction Packet: {identifier}", f"Status: {packet.get('status', 'unknown')}"]
    claims = packet.get("normalized_claims", packet.get("claims", ()))
    if isinstance(claims, Sequence) and not isinstance(claims, (str, bytes)):
        for index, raw in enumerate(claims, start=1):
            if not isinstance(raw, Mapping):
                continue
            lines.extend(
                (
                    f"## Claim {index}: {raw.get('claim_id', 'unknown')}",
                    f"Statement: {raw.get('subject', '')} {raw.get('predicate', '')} {raw.get('value', '')}",
                    f"Polarity: {raw.get('polarity', 'unknown')}",
                    "Applicability: "
                    + ", ".join(
                        f"{name}={raw.get(name, '')}"
                        for name in ("scope", "version", "time_range", "platform", "condition_mode", "modality")
                    ),
                )
            )
            conditions = raw.get("conditions", ())
            if isinstance(conditions, Sequence) and not isinstance(conditions, (str, bytes)):
                lines.append("Conditions: " + ", ".join(str(value) for value in conditions))

    source_refs = packet.get("source_refs", {})
    if isinstance(source_refs, Mapping):
        for claim_id in sorted(source_refs):
            source = source_refs[claim_id]
            if not isinstance(source, Mapping):
                continue
            clusters = source.get("provenance_clusters", ())
            passages = source.get("passages", ())
            cluster_text = (
                ", ".join(str(value) for value in clusters)
                if isinstance(clusters, Sequence) and not isinstance(clusters, (str, bytes))
                else str(clusters)
            )
            passage_text = (
                " | ".join(str(value) for value in passages)
                if isinstance(passages, Sequence) and not isinstance(passages, (str, bytes))
                else str(passages)
            )
            lines.append(f"Source {claim_id}: provenance={cluster_text}; passage={passage_text}")

    dimensions = packet.get("scope_dimensions", ())
    if isinstance(dimensions, Sequence) and not isinstance(dimensions, (str, bytes)):
        lines.append("## Tested Scope")
        for raw in dimensions:
            if not isinstance(raw, Mapping):
                continue
            state = "overlap" if raw.get("overlap") else "separated"
            lines.append(
                f"- {raw.get('dimension', 'dimension')} scope: {state}; "
                f"left={raw.get('left', '')}; right={raw.get('right', '')}; {raw.get('explanation', '')}"
            )

    values = packet.get("conflicting_values", ())
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        lines.append("Conflicting values: " + ", ".join(str(value) for value in values))
    unresolved = packet.get("unresolved_dimensions", ())
    if isinstance(unresolved, Sequence) and not isinstance(unresolved, (str, bytes)):
        lines.append("Unresolved dimensions: " + ", ".join(str(value) for value in unresolved))

    invalidated = packet.get("invalidated_refs", ())
    if isinstance(invalidated, Sequence) and not isinstance(invalidated, (str, bytes)):
        lines.append("invalidated revisions:")
        for raw in invalidated:
            if isinstance(raw, Mapping):
                lines.append(f"- {raw.get('round_id', '')}/{raw.get('artifact_id', '')}@{raw.get('revision', '')}")
            else:
                lines.append(f"- {raw}")

    lines.extend(
        (
            f"Resolution path: {packet.get('resolution_path', 'independent source, revision, method, or experiment')}",
            f"Safe fallback: {packet.get('safe_fallback', 'retain the reversible fallback')}",
            "Blocked operations: decision convergence, readiness, delivery, closure, task release, and completion",
        )
    )
    return "\n".join(lines)


__all__ = [
    "ClaimBoundary",
    "ContradictionPacket",
    "ContradictionDetector",
    "ContradictionStatus",
    "blocking_contradictions",
    "claim_from_mapping",
    "detect_contradictions",
    "derive_contradiction_packets",
    "invalidating_contradictions",
    "render_contradiction_packet",
    "unresolved_claim_ids",
]
