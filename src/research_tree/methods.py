"""Typed method/tool registry for acquisition and method switching."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable, Mapping


class MethodError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MethodSpec:
    method_id: str
    kind: str
    capabilities: tuple[str, ...]
    permission_profile_id: str
    timeout_seconds: int
    retryable: bool = True
    limitation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"capabilities": list(self.capabilities)}


class MethodRegistry:
    def __init__(self, methods: Iterable[MethodSpec] = ()) -> None:
        self._methods: dict[str, MethodSpec] = {}
        for method in methods:
            self.register(method)

    def register(self, method: MethodSpec) -> None:
        if not method.method_id or method.method_id in self._methods:
            raise MethodError("method_id is empty or already registered")
        if method.timeout_seconds < 1:
            raise MethodError("method timeout must be positive")
        self._methods[method.method_id] = method

    def get(self, method_id: str) -> MethodSpec:
        try:
            return self._methods[method_id]
        except KeyError as exc:
            raise MethodError(f"unknown method: {method_id}") from exc

    def candidates(self, capability: str, *, exclude: Iterable[str] = ()) -> tuple[MethodSpec, ...]:
        excluded = set(exclude)
        return tuple(method for method in self._methods.values() if capability in method.capabilities and method.method_id not in excluded)

    def switch(self, failed_method_id: str, capability: str) -> MethodSpec:
        candidates = self.candidates(capability, exclude=(failed_method_id,))
        if not candidates:
            raise MethodError(f"no alternate method for {capability}")
        return sorted(candidates, key=lambda item: item.method_id)[0]

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "methods": [method.to_dict() for method in sorted(self._methods.values(), key=lambda item: item.method_id)]}
