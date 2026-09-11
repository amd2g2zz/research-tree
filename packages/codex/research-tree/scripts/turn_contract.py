"""Two-layer contract seam: contract terms, trace-type registry, trace verification.

ADR-008 (issue #501): the engine gates ONLY on structural traces — artifacts
whose existence and schema it can verify — while the prompt layer carries all
open-ended behavior strategy (interview craft, teaching, counterexamples,
persona). Contract terms and trace types are the ONLY enumerated space;
behaviors are never enumerated.

Per alignment turn: (1) the engine emits contract terms (``target_gap`` /
``required_traces`` / ``cost_cap`` / ``taboos``); (2) the prompt layer composes
the turn freely against those terms; (3) :func:`verify_traces` checks the
turn's recorded traces — presence and schema only, never content quality
(missing trace = gate failure naming the exact term); (4) the caller persists
the turn-record with terms, traces, and the user-response class (#497).

SEAM ONLY: nothing in ``alignment_graph.py``, ``decision_frame.py``, or
``lifecycle_hook.py`` is wired to this module yet — that rewiring belongs to
issues #489/#490. Stdlib-only per ADR-001; validates with the repository's
whitelist pattern (strict key sets, errors naming the offending field) until
ADR-007's pydantic boundary gains its first runtime consumer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "DEFAULT_MAX_CHARS_PER_TURN",
    "DEFAULT_MAX_QUESTIONS_PER_TURN",
    "DEFAULT_TRACE_REGISTRY",
    "INITIAL_TRACE_TYPES",
    "RESPONSE_CLASSES",
    "RESPONSE_CLASS_DISCRIMINATION",
    "RESPONSE_CLASS_GENERATION",
    "SCHEMA_VERSION",
    "AgentTurnBudget",
    "ContractTerms",
    "ContractTermsError",
    "CostCap",
    "DuplicateTraceTypeError",
    "MissingTraceError",
    "TraceRecordError",
    "TraceRegistryError",
    "TraceType",
    "TraceTypeRegistry",
    "verify_traces",
]

SCHEMA_VERSION = 1

# Issue #527 — the agent turn budget, the dual of the user-side cost_cap:
# where ``CostCap`` bounds the requester's response production, the
# ``AgentTurnBudget`` bounds the agent's own output per interactive turn.
# ``max_questions = 1`` is the one-question-per-turn invariant behind the
# #514 shape gate's flag; ``max_chars`` is tier-settable (#526) — these
# constants are the engine floor the terms are emitted with.
DEFAULT_MAX_QUESTIONS_PER_TURN = 1
DEFAULT_MAX_CHARS_PER_TURN = 1200

RESPONSE_CLASS_DISCRIMINATION = "discrimination"
RESPONSE_CLASS_GENERATION = "generation"
RESPONSE_CLASSES = (RESPONSE_CLASS_DISCRIMINATION, RESPONSE_CLASS_GENERATION)

# Mirrors alignment_graph.IDENTIFIER_RE. Kept local so this seam does not
# import the sqlite-backed graph module it will eventually gate (#489).
NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TRACE_TYPE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class TurnContractError(ValueError):
    """Base error for the two-layer contract seam."""


class ContractTermsError(TurnContractError):
    """A contract-terms payload violates the terms schema."""


class TraceRegistryError(TurnContractError):
    """A trace-type declaration or registry operation is invalid."""


class DuplicateTraceTypeError(TraceRegistryError):
    """A trace type was registered under a name that already exists."""


class TraceRecordError(TurnContractError):
    """A recorded trace is unregistered or violates its type's schema."""


class MissingTraceError(TurnContractError):
    """A required contract trace is absent from the recorded turn traces."""


@dataclass(frozen=True, slots=True)
class CostCap:
    """User response-production ceiling for one turn.

    The cap models bytes-to-decide, not bytes-to-read: a ``discrimination``
    response (point at an option, confirm/deny) is capped at exactly one
    sentence (辨别类 ≤ 一句指认); a ``generation`` response may carry free
    text, bounded only by an explicit optional sentence budget.
    """

    response_class: str
    max_sentences: int | None

    def __post_init__(self) -> None:
        if self.response_class not in RESPONSE_CLASSES:
            raise ContractTermsError(
                f"cost_cap response_class must be one of {RESPONSE_CLASSES}: {self.response_class!r}"
            )
        if isinstance(self.max_sentences, bool) or not (
            self.max_sentences is None or isinstance(self.max_sentences, int)
        ):
            raise ContractTermsError("cost_cap max_sentences must be None or an integer")
        if self.response_class == RESPONSE_CLASS_DISCRIMINATION and self.max_sentences != 1:
            raise ContractTermsError("cost_cap max_sentences must be exactly 1 for discrimination responses")
        if self.response_class == RESPONSE_CLASS_GENERATION and self.max_sentences is not None:
            if self.max_sentences < 1:
                raise ContractTermsError("cost_cap max_sentences must be positive for generation responses")

    def to_dict(self) -> dict[str, Any]:
        return {"response_class": self.response_class, "max_sentences": self.max_sentences}

    @classmethod
    def from_dict(cls, value: Any) -> "CostCap":
        if not isinstance(value, Mapping) or set(value) != {"response_class", "max_sentences"}:
            raise ContractTermsError("cost_cap must contain exactly response_class and max_sentences")
        return cls(response_class=value["response_class"], max_sentences=value["max_sentences"])


@dataclass(frozen=True, slots=True)
class AgentTurnBudget:
    """Agent output ceiling for one turn (issue #527) — the dual of CostCap.

    At most ``max_questions`` questions per interactive turn and at most
    ``max_chars`` characters of composed output. Carried in the emitted
    ``ContractTerms`` next to the user-side ``cost_cap`` and verified at
    record time as a flag-not-block violation stream (#525 counts it);
    exceeding it splits the turn, never truncates or blocks it.
    """

    max_questions: int
    max_chars: int

    def __post_init__(self) -> None:
        for name in ("max_questions", "max_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ContractTermsError(f"agent_turn_budget {name} must be a positive integer: {value!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"max_questions": self.max_questions, "max_chars": self.max_chars}

    @classmethod
    def from_dict(cls, value: Any) -> "AgentTurnBudget":
        if not isinstance(value, Mapping) or set(value) != {"max_questions", "max_chars"}:
            raise ContractTermsError("agent_turn_budget must contain exactly max_questions and max_chars")
        return cls(max_questions=value["max_questions"], max_chars=value["max_chars"])


@dataclass(frozen=True, slots=True)
class TraceType:
    """One structural artifact kind the engine can verify.

    ``required_fields`` declares the payload's structural keys; verification
    checks their presence and never their content.
    """

    name: str
    required_fields: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or TRACE_TYPE_RE.fullmatch(self.name) is None:
            raise TraceRegistryError(f"trace type name must match {TRACE_TYPE_RE.pattern}: {self.name!r}")
        fields = tuple(self.required_fields)
        if any(not isinstance(item, str) or not item for item in fields):
            raise TraceRegistryError(f"trace type {self.name} required_fields must be non-empty strings")
        if len(set(fields)) != len(fields):
            raise TraceRegistryError(f"trace type {self.name} required_fields must be unique")
        object.__setattr__(self, "required_fields", fields)
        if not isinstance(self.description, str):
            raise TraceRegistryError(f"trace type {self.name} description must be a string")


class TraceTypeRegistry:
    """Frozen, append-only registry of verifiable trace types.

    The registry is an immutable value: :meth:`register` returns a NEW
    registry containing the addition; there is no unregister or redefine
    path. Later waves (#493/#498/#499) append entries and can never silently
    weaken an existing type's schema.
    """

    __slots__ = ("_types",)

    def __init__(self, trace_types: Iterable[TraceType] = ()) -> None:
        types: dict[str, TraceType] = {}
        for trace_type in trace_types:
            if not isinstance(trace_type, TraceType):
                raise TraceRegistryError(f"registry entries must be TraceType values: {trace_type!r}")
            if trace_type.name in types:
                raise DuplicateTraceTypeError(f"duplicate trace type registration: {trace_type.name}")
            types[trace_type.name] = trace_type
        self._types = types

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._types))

    def get(self, name: str) -> TraceType:
        try:
            return self._types[name]
        except KeyError:
            raise TraceRegistryError(f"unregistered trace type: {name!r}") from None

    def __contains__(self, name: object) -> bool:
        return name in self._types

    def __len__(self) -> int:
        return len(self._types)

    def register(self, trace_type: TraceType) -> "TraceTypeRegistry":
        if not isinstance(trace_type, TraceType):
            raise TraceRegistryError(f"registry entries must be TraceType values: {trace_type!r}")
        if trace_type.name in self._types:
            raise DuplicateTraceTypeError(f"duplicate trace type registration: {trace_type.name}")
        return TraceTypeRegistry((*self._types.values(), trace_type))


def _initial_type(name: str, required_field: str, description: str) -> TraceType:
    return TraceType(name=name, required_fields=(required_field,), description=description)


# The six initial trace types named by issue #501. Each declares one minimal
# structural key; append-only registration (never redefinition) extends them.
DEFAULT_TRACE_REGISTRY = TraceTypeRegistry(
    (
        _initial_type("option-set", "options", "show-then-point option set offered to the user"),
        _initial_type("concept-card", "concept", "concept card teaching one idea"),
        _initial_type("guess-statement", "guess", "agent echo-guess of the user's intent"),
        _initial_type("counterargument", "counterargument", "counterargument carried by a strategy display"),
        _initial_type("possibility-survey", "possibilities", "survey of the possibility space before an open question"),
        _initial_type("evidence-delta", "delta", "what evidence changed on this turn"),
        # Issue #498: bidirectional complexity-constraint proportionality
        # check (over-engineering AND under-proportioned constraints). The
        # engine verifies presence + schema of the four structural fields;
        # the judgment content is prompt-layer craft (layer 1 of the ladder —
        # waiver on insistence and compile-time conflict rejection already
        # exist as layers 2-3).
        TraceType(
            name="proportionality_assessment",
            required_fields=("direction", "finding", "alternative", "reframing"),
            description="complexity-constraint proportionality: over/under direction, named "
            "simpler-alternative or magnitude conflict, nearest-feasible reframing",
        ),
        # Issue #499: mid-research user-update shapes. ``digest-first`` is the
        # one-point digest (point + decision relevance + source pointer);
        # ``viewpoint-hints`` reuses the material_alternatives / trade_off
        # schema shape for 2-3 viewpoint hints with trade-offs. Presence and
        # schema only — composition stays prompt-layer craft.
        TraceType(
            name="digest-first",
            required_fields=("point", "decision_relevance", "source_pointer"),
            description="digest-first user update: 1-2 sentence point + decision relevance + source pointer",
        ),
        _initial_type(
            "viewpoint-hints",
            "alternatives",
            "distinct positions with trade-offs, material_alternatives/trade_off schema shape",
        ),
    )
)

INITIAL_TRACE_TYPES: tuple[str, ...] = DEFAULT_TRACE_REGISTRY.names()


@dataclass(frozen=True, slots=True)
class ContractTerms:
    """Structured contract terms the engine emits for the next turn.

    The four canonical terms plus a schema version, and the #527 agent-side
    additions: ``agent_turn_budget`` (the dual of ``cost_cap``) and the
    required-trace deferral queue. ``required_traces`` may be empty (a turn
    with no structural gate); every declared name must be registered. The
    new fields are additive: legacy terms without them keep parsing.
    """

    target_gap: str
    required_traces: tuple[str, ...]
    cost_cap: CostCap
    taboos: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION
    agent_turn_budget: AgentTurnBudget | None = None
    deferred_traces: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise ContractTermsError(f"contract terms schema_version must be {SCHEMA_VERSION}")
        if not isinstance(self.target_gap, str) or NODE_ID_RE.fullmatch(self.target_gap) is None:
            raise ContractTermsError(f"target_gap must be an alignment-graph node id: {self.target_gap!r}")
        if not isinstance(self.cost_cap, CostCap):
            raise ContractTermsError(f"cost_cap must be a CostCap: {self.cost_cap!r}")
        if self.agent_turn_budget is not None and not isinstance(self.agent_turn_budget, AgentTurnBudget):
            raise ContractTermsError(f"agent_turn_budget must be an AgentTurnBudget: {self.agent_turn_budget!r}")
        traces = tuple(self.required_traces)
        if any(not isinstance(item, str) or not item for item in traces):
            raise ContractTermsError("required_traces must be non-empty strings")
        if len(set(traces)) != len(traces):
            raise ContractTermsError(f"required_traces must be unique: duplicate in {list(traces)}")
        for name in traces:
            if name not in DEFAULT_TRACE_REGISTRY:
                raise ContractTermsError(f"required_traces references unregistered trace type: {name}")
        object.__setattr__(self, "required_traces", traces)
        deferred = tuple(self.deferred_traces)
        if any(not isinstance(item, str) or not item for item in deferred):
            raise ContractTermsError("deferred_traces must be non-empty strings")
        if len(set(deferred)) != len(deferred):
            raise ContractTermsError(f"deferred_traces must be unique: duplicate in {list(deferred)}")
        for name in deferred:
            if name not in DEFAULT_TRACE_REGISTRY:
                raise ContractTermsError(f"deferred_traces references unregistered trace type: {name}")
        overlap = set(deferred) & set(traces)
        if overlap:
            raise ContractTermsError(f"deferred_traces must be disjoint from required_traces: {sorted(overlap)}")
        object.__setattr__(self, "deferred_traces", deferred)
        taboos = tuple(self.taboos)
        if any(not isinstance(item, str) or NODE_ID_RE.fullmatch(item) is None for item in taboos):
            raise ContractTermsError(f"taboos entries must be alignment-graph node ids: {list(taboos)}")
        if len(set(taboos)) != len(taboos):
            raise ContractTermsError(f"taboos entries must be unique: duplicate in {list(taboos)}")
        object.__setattr__(self, "taboos", taboos)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_gap": self.target_gap,
            "required_traces": list(self.required_traces),
            "cost_cap": self.cost_cap.to_dict(),
            "taboos": list(self.taboos),
            "agent_turn_budget": (self.agent_turn_budget.to_dict() if self.agent_turn_budget is not None else None),
            "deferred_traces": list(self.deferred_traces),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ContractTerms":
        core = {"schema_version", "target_gap", "required_traces", "cost_cap", "taboos"}
        optional = {"agent_turn_budget", "deferred_traces"}
        if not isinstance(value, Mapping):
            raise ContractTermsError("contract terms must be a mapping")
        missing = core - set(value)
        unknown = set(value) - core - optional
        if missing or unknown:
            raise ContractTermsError(
                f"contract terms field mismatch; missing: {sorted(missing)}, unknown: {sorted(unknown)}"
            )
        required = value["required_traces"]
        taboos = value["taboos"]
        if not isinstance(required, (list, tuple)) or not isinstance(taboos, (list, tuple)):
            raise ContractTermsError("required_traces and taboos must be lists")
        budget_value = value.get("agent_turn_budget")
        deferred = value.get("deferred_traces", ())
        if not isinstance(deferred, (list, tuple)):
            raise ContractTermsError("deferred_traces must be a list")
        return cls(
            target_gap=value["target_gap"],
            required_traces=tuple(required),
            cost_cap=CostCap.from_dict(value["cost_cap"]),
            taboos=tuple(taboos),
            schema_version=value["schema_version"],
            agent_turn_budget=None if budget_value is None else AgentTurnBudget.from_dict(budget_value),
            deferred_traces=tuple(deferred),
        )


def verify_traces(terms: ContractTerms, traces: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Verify recorded turn traces against emitted contract terms.

    Presence and schema checks only: every required trace type must be present
    among the recorded traces, every recorded trace type must be registered,
    and every trace payload must carry its type's declared required fields.
    Content quality is never inspected (ADR-008). Returns the satisfied
    required-trace names in declared order; fails closed naming the exact
    missing term.
    """
    recorded: dict[str, list[Mapping[str, Any]]] = {}
    for index, trace in enumerate(traces):
        if not isinstance(trace, Mapping) or set(trace) != {"type", "payload"}:
            raise TraceRecordError(f"trace record {index} must contain exactly type and payload")
        name = trace["type"]
        if not isinstance(name, str) or name not in DEFAULT_TRACE_REGISTRY:
            raise TraceRecordError(f"trace record {index} has an unregistered trace type: {name!r}")
        payload = trace["payload"]
        if not isinstance(payload, Mapping):
            raise TraceRecordError(f"trace record {index} payload must be a mapping")
        trace_type = DEFAULT_TRACE_REGISTRY.get(name)
        for required_field in trace_type.required_fields:
            if required_field not in payload:
                raise TraceRecordError(
                    f"trace record {index} ({name}) is missing required payload field: {required_field}"
                )
        recorded.setdefault(name, []).append(payload)
    satisfied: list[str] = []
    for name in terms.required_traces:
        if not recorded.get(name):
            raise MissingTraceError(f"turn is missing required trace: {name}")
        satisfied.append(name)
    return tuple(satisfied)
