"""Canonical contradiction classification for grounded research claims."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
import re
from typing import Any, Iterable, Mapping, Sequence

from .claims import Claim


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
class ContradictionPacket:
    claim_ids: tuple[str, ...]
    status: ContradictionStatus
    reason: str
    conflicting_values: tuple[str, ...] = ()

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


def _same_subject_predicate(left: Claim, right: Claim) -> bool:
    return (left.subject.casefold(), left.predicate.casefold()) == (
        right.subject.casefold(),
        right.predicate.casefold(),
    )


def _same_applicability(left: Claim, right: Claim) -> bool:
    return (
        left.scope == right.scope
        and left.version == right.version
        and left.time_range == right.time_range
        and left.platform == right.platform
        and left.modality == right.modality
        and set(left.conditions) == set(right.conditions)
    )


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


def derive_contradiction_packets(claims: Iterable[Claim]) -> tuple[ContradictionPacket, ...]:
    """Derive deterministic conflicts without trusting worker option effects."""

    values = tuple(claims)
    if any(not isinstance(claim, Claim) for claim in values):
        raise ValueError("claims must contain Claim values")
    packets: list[ContradictionPacket] = []
    material_groups: dict[tuple[str, ...], list[Claim]] = {}
    for left, right in combinations(values, 2):
        if not _same_subject_predicate(left, right) or not _conflicts(left, right):
            continue
        if _same_applicability(left, right):
            key = (
                left.subject.casefold(),
                left.predicate.casefold(),
                left.scope,
                left.version,
                left.time_range,
                left.platform,
                left.modality,
                *sorted(left.conditions),
            )
            material_groups.setdefault(key, [])
            for claim in (left, right):
                if claim not in material_groups[key]:
                    material_groups[key].append(claim)
        else:
            packets.append(
                ContradictionPacket(
                    tuple(sorted((left.claim_id, right.claim_id))),
                    ContradictionStatus.SCOPE_SEPARATED,
                    "non-overlapping-applicability",
                    tuple(sorted((left.value, right.value))),
                )
            )
    for group in material_groups.values():
        packets.append(
            ContradictionPacket(
                tuple(sorted(claim.claim_id for claim in group)),
                ContradictionStatus.CONTESTED,
                "incompatible-applicable-claims",
                tuple(sorted({claim.value for claim in group})),
            )
        )
    return tuple(sorted(packets, key=lambda packet: packet.claim_ids))


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


__all__ = [
    "ContradictionPacket",
    "ContradictionStatus",
    "claim_from_mapping",
    "derive_contradiction_packets",
    "unresolved_claim_ids",
]
