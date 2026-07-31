"""Safe, run-scoped Context Pack intake and repository reconnaissance."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess
from typing import Iterable, Sequence

from .domain import (
    ArtifactRef,
    ArtifactRevision,
    RuntimeStoreError,
    canonical_json_bytes,
    utc_now,
    validate_identifier,
)
from .storage import RunStore


INPUT_LEDGER_ARTIFACT_KIND = "input-ledger-entry"

INPUT_KINDS = frozenset(
    {
        "brief",
        "article",
        "note",
        "draft",
        "repository",
        "log",
        "prior_output",
        "feedback",
        "context_bundle",
        "other",
    }
)
TEXT_INPUT_KINDS = INPUT_KINDS - {"repository", "context_bundle"}
ORIGIN_TYPES = frozenset({"user", "workspace", "url", "repository", "generated"})
INPUT_ROLES = frozenset({"baseline", "constraint", "signal", "evidence", "history"})
GROUPINGS = frozenset({"user_provided", "agent_composed", "none"})


DEFAULT_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node-modules",
        "node_modules",
        "venv",
    }
)
DEFAULT_SECRET_FILENAMES = frozenset(
    {
        ".env",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
    }
)
DEFAULT_SECRET_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
DEFAULT_BINARY_SUFFIXES = frozenset(
    {
        ".7z",
        ".bin",
        ".class",
        ".dll",
        ".dylib",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".lockb",
        ".mp3",
        ".mp4",
        ".o",
        ".pdf",
        ".png",
        ".so",
        ".tar",
        ".wasm",
        ".webp",
        ".zip",
    }
)
SOURCE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".swift",
        ".ts",
        ".tsx",
    }
)
DEPENDENCY_FILENAMES = frozenset(
    {
        "cargo.toml",
        "composer.json",
        "gemfile",
        "go.mod",
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "pom.xml",
        "pyproject.toml",
        "requirements.txt",
        "setup.cfg",
        "setup.py",
        "uv.lock",
        "yarn.lock",
    }
)
DEPLOYMENT_FILENAMES = frozenset(
    {
        "azure-pipelines.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "dockerfile",
        "fly.toml",
        ".gitlab-ci.yml",
        "netlify.toml",
        "procfile",
        "serverless.yml",
        "vercel.json",
    }
)
ENTRYPOINT_FILENAMES = frozenset(
    {
        "__main__.py",
        "app.py",
        "index.js",
        "index.ts",
        "main.go",
        "main.py",
        "main.rs",
        "main.ts",
        "server.js",
        "server.py",
        "server.ts",
    }
)


class IntakeError(RuntimeStoreError):
    """Base error for invalid Context Pack intake requests."""


class InvalidInputError(IntakeError):
    """Raised when a single input cannot satisfy the ledger contract."""


class InvalidContextBundleError(IntakeError):
    """Raised when Context Bundle membership cannot be represented safely."""


class RepositoryIntakeError(IntakeError):
    """Raised when a repository root itself is not a readable directory."""


@dataclass(frozen=True, slots=True)
class RepositorySafetyPolicy:
    """Explicit resource and path limits for read-only repository inspection."""

    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 5_000_000
    max_files: int = 2_000
    excluded_directories: frozenset[str] = field(
        default_factory=lambda: DEFAULT_EXCLUDED_DIRECTORIES
    )
    secret_filenames: frozenset[str] = field(default_factory=lambda: DEFAULT_SECRET_FILENAMES)
    secret_suffixes: frozenset[str] = field(default_factory=lambda: DEFAULT_SECRET_SUFFIXES)
    binary_suffixes: frozenset[str] = field(default_factory=lambda: DEFAULT_BINARY_SUFFIXES)

    def __post_init__(self) -> None:
        for label, value in (
            ("max_file_bytes", self.max_file_bytes),
            ("max_total_bytes", self.max_total_bytes),
            ("max_files", self.max_files),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidInputError(f"{label} must be a positive integer")
        object.__setattr__(
            self,
            "excluded_directories",
            frozenset(name.lower() for name in self.excluded_directories),
        )
        object.__setattr__(
            self,
            "secret_filenames",
            frozenset(name.lower() for name in self.secret_filenames),
        )
        object.__setattr__(
            self,
            "secret_suffixes",
            frozenset(suffix.lower() for suffix in self.secret_suffixes),
        )
        object.__setattr__(
            self,
            "binary_suffixes",
            frozenset(suffix.lower() for suffix in self.binary_suffixes),
        )


@dataclass(slots=True)
class _BaselineBuilder:
    root: Path
    policy: RepositorySafetyPolicy
    anchors: list[dict[str, str | None]] = field(default_factory=list)
    facts: list[dict[str, object]] = field(default_factory=list)
    unreadable: list[dict[str, str]] = field(default_factory=list)
    file_hashes: list[tuple[str, str]] = field(default_factory=list)
    seen_files: set[str] = field(default_factory=set)
    seen_anchors: set[tuple[str, str | None]] = field(default_factory=set)
    seen_facts: set[tuple[str, str, str | None]] = field(default_factory=set)
    seen_unreadable: set[tuple[str, str]] = field(default_factory=set)
    total_bytes: int = 0
    inspected_files: int = 0
    limit_reached: bool = False

    def add_anchor(self, path: str, symbol: str | None = None) -> None:
        key = (path, symbol)
        if key not in self.seen_anchors:
            self.seen_anchors.add(key)
            self.anchors.append({"path": path, "symbol": symbol})

    def add_fact(
        self,
        category: str,
        path: str,
        observation: str,
        symbol: str | None = None,
    ) -> None:
        key = (category, path, symbol)
        if key in self.seen_facts:
            return
        self.seen_facts.add(key)
        self.add_anchor(path, symbol)
        self.facts.append(
            {
                "category": category,
                "anchor": {"path": path, "symbol": symbol},
                "observation": observation,
            }
        )

    def add_unreadable(self, path: str, reason: str) -> None:
        key = (path, reason)
        if key not in self.seen_unreadable:
            self.seen_unreadable.add(key)
            self.unreadable.append({"path": path, "reason": reason})

    def content_fingerprint(self) -> str:
        digest = sha256()
        for path, content_hash in sorted(self.file_hashes):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(content_hash.encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()


class RepositoryInspector:
    """Inspect a local repository without following links or running project code."""

    def __init__(self, policy: RepositorySafetyPolicy | None = None) -> None:
        self._policy = policy or RepositorySafetyPolicy()

    def inspect(
        self,
        repository_root: str | Path,
        *,
        include_paths: Iterable[str | Path] | None = None,
    ) -> dict[str, object]:
        requested_root = Path(repository_root).expanduser()
        if requested_root.is_symlink():
            raise RepositoryIntakeError("repository root cannot be a symlink")
        root = requested_root.resolve(strict=False)
        if not root.exists() or not root.is_dir():
            raise RepositoryIntakeError(f"repository root is not a readable directory: {repository_root}")

        builder = _BaselineBuilder(root=root, policy=self._policy)
        selected_paths = self._selected_paths(root, include_paths)
        for selected_path in selected_paths:
            self._inspect_scope(root, selected_path, builder)

        observed_at = utc_now()
        fingerprint = builder.content_fingerprint()
        revision = self._git_revision(root)
        revision.update({"sha256": fingerprint, "observed_at": observed_at})
        return {
            "repository_root": str(root),
            "read_scope": [self._scope_label(root, path) for path in selected_paths],
            "revision": revision,
            "anchors": sorted(
                builder.anchors,
                key=lambda anchor: (str(anchor["path"]), str(anchor["symbol"] or "")),
            ),
            "facts": sorted(
                builder.facts,
                key=lambda fact: (
                    str(fact["category"]),
                    str(fact["anchor"]["path"]),  # type: ignore[index]
                    str(fact["anchor"]["symbol"] or ""),  # type: ignore[index]
                ),
            ),
            "unreadable": sorted(
                builder.unreadable,
                key=lambda item: (item["path"], item["reason"]),
            ),
        }

    def _selected_paths(
        self,
        root: Path,
        include_paths: Iterable[str | Path] | None,
    ) -> tuple[Path, ...]:
        if include_paths is None:
            return (Path("."),)
        if isinstance(include_paths, (str, Path)):
            return (Path(include_paths),)
        return tuple(Path(item) for item in include_paths)

    def _inspect_scope(self, root: Path, requested: Path, builder: _BaselineBuilder) -> None:
        display = self._display_scope(requested)
        candidate = requested if requested.is_absolute() else root / requested
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            builder.add_unreadable(display, "unreadable_path")
            return
        if not self._is_within_root(root, resolved):
            builder.add_unreadable(display, "outside_repository")
            return
        if candidate.is_symlink():
            self._record_symlink(root, candidate, display, builder)
            return
        if not candidate.exists():
            builder.add_unreadable(display, "missing_path")
            return
        if candidate.is_file():
            self._inspect_file(root, candidate, builder)
            return
        if not candidate.is_dir():
            builder.add_unreadable(display, "nonregular_file")
            return

        for directory, directories, filenames in os.walk(candidate, followlinks=False):
            current = Path(directory)
            directories.sort()
            filenames.sort()
            retained_directories: list[str] = []
            for name in directories:
                child = current / name
                relative = self._relative_path(root, child)
                if child.is_symlink():
                    self._record_symlink(root, child, relative, builder)
                elif name.lower() in self._policy.excluded_directories:
                    builder.add_unreadable(relative, "excluded_directory")
                else:
                    retained_directories.append(name)
            directories[:] = retained_directories

            for name in filenames:
                self._inspect_file(root, current / name, builder)

    def _inspect_file(self, root: Path, candidate: Path, builder: _BaselineBuilder) -> None:
        relative = self._relative_path(root, candidate)
        if relative in builder.seen_files:
            return
        builder.seen_files.add(relative)
        try:
            if candidate.is_symlink():
                self._record_symlink(root, candidate, relative, builder)
                return
            if self._is_secret_path(candidate, relative):
                builder.add_unreadable(relative, "secret")
                return
            file_stat = candidate.stat()
        except OSError:
            builder.add_unreadable(relative, "unreadable_path")
            return
        if not stat.S_ISREG(file_stat.st_mode):
            builder.add_unreadable(relative, "nonregular_file")
            return
        if builder.limit_reached:
            builder.add_unreadable(relative, "scan_file_limit")
            return
        builder.inspected_files += 1
        if builder.inspected_files > self._policy.max_files:
            builder.limit_reached = True
            builder.add_unreadable(relative, "scan_file_limit")
            return
        if file_stat.st_size > self._policy.max_file_bytes:
            builder.add_unreadable(relative, "too_large")
            return
        if builder.total_bytes + file_stat.st_size > self._policy.max_total_bytes:
            builder.add_unreadable(relative, "scan_budget_exceeded")
            return
        if candidate.suffix.lower() in self._policy.binary_suffixes:
            builder.add_unreadable(relative, "binary")
            return
        try:
            with candidate.open("rb") as handle:
                content = handle.read(self._policy.max_file_bytes + 1)
        except OSError:
            builder.add_unreadable(relative, "unreadable_path")
            return
        if len(content) > self._policy.max_file_bytes:
            builder.add_unreadable(relative, "too_large")
            return
        if builder.total_bytes + len(content) > self._policy.max_total_bytes:
            builder.add_unreadable(relative, "scan_budget_exceeded")
            return
        if b"\0" in content[:8192]:
            builder.add_unreadable(relative, "binary")
            return
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            builder.add_unreadable(relative, "unreadable_encoding")
            return

        builder.total_bytes += len(content)
        builder.file_hashes.append((relative, sha256(content).hexdigest()))
        self._record_facts(relative, text, builder)

    def _record_facts(self, relative: str, content: str, builder: _BaselineBuilder) -> None:
        path = Path(relative)
        filename = path.name.lower()
        suffix = path.suffix.lower()
        path_parts = {part.lower() for part in path.parts}
        builder.add_fact("path", relative, "readable file within the selected repository scope")

        is_source = suffix in SOURCE_SUFFIXES
        is_test = (
            filename.startswith("test_")
            or filename.endswith("_test.py")
            or "test" in path_parts
            or "tests" in path_parts
            or "spec" in path_parts
            or "specs" in path_parts
        )
        is_dependency = filename in DEPENDENCY_FILENAMES or filename.startswith("requirements")
        is_deployment = (
            filename in DEPLOYMENT_FILENAMES
            or ".github" in path_parts and "workflows" in path_parts
            or suffix == ".tf"
            or "k8s" in path_parts
            or "kubernetes" in path_parts
            or "helm" in path_parts
        )
        is_interface = suffix == ".proto" or filename.startswith("openapi") or filename.startswith("asyncapi")
        is_entry_point = filename in ENTRYPOINT_FILENAMES

        if is_source:
            builder.add_fact("source", relative, "source file identified by extension")
        if is_test:
            builder.add_fact("test", relative, "test path identified by filename or directory")
        if is_dependency:
            builder.add_fact("dependency", relative, "dependency or package manifest identified by filename")
        if is_deployment:
            builder.add_fact("deployment", relative, "deployment or CI configuration identified by path")
        if is_interface:
            builder.add_fact("interface", relative, "interface definition identified by filename or extension")
        if is_entry_point:
            builder.add_fact("entry_point", relative, "candidate entry point by filename")
            builder.add_fact("behavior", relative, "candidate runtime behavior entry point by filename")
        if is_source or is_test or is_dependency or is_deployment or is_interface:
            builder.add_fact(
                "change_surface",
                relative,
                "candidate change surface based on repository role",
            )
        if suffix == ".py":
            self._record_python_symbols(relative, content, builder)

    @staticmethod
    def _record_python_symbols(relative: str, content: str, builder: _BaselineBuilder) -> None:
        try:
            module = ast.parse(content, filename=relative)
        except (SyntaxError, ValueError):
            return
        for node in module.body:
            if isinstance(node, ast.ClassDef):
                builder.add_fact("symbol", relative, "top-level Python class", node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                builder.add_fact("symbol", relative, "top-level Python function", node.name)

    def _record_symlink(
        self,
        root: Path,
        candidate: Path,
        display: str,
        builder: _BaselineBuilder,
    ) -> None:
        try:
            target = candidate.resolve(strict=False)
        except OSError:
            builder.add_unreadable(display, "unreadable_path")
            return
        reason = self.symlink_reason(root, target)
        builder.add_unreadable(display, reason)

    @staticmethod
    def symlink_reason(repository_root: str | Path, resolved_target: str | Path) -> str:
        """Classify a resolved link target without opening either path."""

        root = Path(repository_root).resolve(strict=False)
        target = Path(resolved_target).resolve(strict=False)
        return "symlink_not_followed" if RepositoryInspector._is_within_root(root, target) else "external_symlink"

    def _git_revision(self, root: Path) -> dict[str, object]:
        inside_repository = self._git(root, "rev-parse", "--is-inside-work-tree")
        if inside_repository != "true":
            return {"branch": None, "commit": None, "dirty": None}
        branch = self._git(root, "branch", "--show-current")
        commit = self._git(root, "rev-parse", "HEAD")
        dirty_output = self._git(root, "status", "--porcelain", "--untracked-files=all")
        return {
            "branch": branch or None,
            "commit": commit or None,
            "dirty": bool(dirty_output) if dirty_output is not None else None,
        }

    @staticmethod
    def _git(root: Path, *arguments: str) -> str | None:
        environment = os.environ.copy()
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        try:
            completed = subprocess.run(
                ["git", "-c", "core.fsmonitor=false", "-C", str(root), *arguments],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                timeout=5,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()

    @staticmethod
    def _is_within_root(root: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(root)
        except ValueError:
            return False
        return True

    @staticmethod
    def _display_scope(path: Path) -> str:
        value = path.as_posix()
        return value if value else "."

    @classmethod
    def _scope_label(cls, root: Path, requested: Path) -> str:
        candidate = requested if requested.is_absolute() else root / requested
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            return cls._display_scope(requested)
        if cls._is_within_root(root, resolved):
            return cls._relative_path(root, resolved)
        return cls._display_scope(requested)

    @staticmethod
    def _relative_path(root: Path, path: Path) -> str:
        return path.relative_to(root).as_posix() or "."

    def _is_secret_path(self, candidate: Path, relative: str) -> bool:
        filename = candidate.name.lower()
        if filename in self._policy.secret_filenames:
            return True
        if filename.startswith(".env.") and not filename.endswith(".example"):
            return True
        if candidate.suffix.lower() in self._policy.secret_suffixes:
            return True
        return any(part.lower() in {".aws", ".ssh", "secrets"} for part in Path(relative).parts)


class InputIntakeService:
    """Append Context Pack inputs to one explicit run store."""

    def __init__(
        self,
        store: RunStore,
        *,
        policy: RepositorySafetyPolicy | None = None,
    ) -> None:
        self._store = store
        self._inspector = RepositoryInspector(policy)

    def ingest_text(
        self,
        *,
        round_id: str,
        input_id: str,
        kind: str,
        content: str,
        origin_type: str,
        origin_locator: str,
        role: str = "signal",
        read_scope: str = "full text",
    ) -> ArtifactRevision:
        self._validate_common_input(
            round_id=round_id,
            input_id=input_id,
            kind=kind,
            origin_type=origin_type,
            origin_locator=origin_locator,
            role=role,
            read_scope=read_scope,
        )
        if kind not in TEXT_INPUT_KINDS:
            raise InvalidInputError(f"ingest_text does not accept input kind: {kind}")
        if not isinstance(content, str):
            raise InvalidInputError("text content must be a string")
        self._ensure_kind_compatibility(round_id, input_id, kind)
        observed_at = utc_now()
        payload = self._ledger_payload(
            round_id=round_id,
            input_id=input_id,
            kind=kind,
            origin_type=origin_type,
            origin_locator=origin_locator,
            revision={
                "branch": None,
                "commit": None,
                "sha256": sha256(content.encode("utf-8")).hexdigest(),
                "observed_at": observed_at,
            },
            read_scope=read_scope,
            role=role,
            material={"kind": "inline-text", "content": content},
        )
        return self._store.append_artifact(
            round_id,
            input_id,
            INPUT_LEDGER_ARTIFACT_KIND,
            payload,
        )

    def ingest_repository(
        self,
        *,
        round_id: str,
        input_id: str,
        repository_root: str | Path,
        origin_type: str,
        role: str = "baseline",
        origin_locator: str | None = None,
        read_scope: str = "repository root (read-only)",
        include_paths: Iterable[str | Path] | None = None,
    ) -> ArtifactRevision:
        locator = origin_locator or str(Path(repository_root).expanduser().resolve(strict=False))
        self._validate_common_input(
            round_id=round_id,
            input_id=input_id,
            kind="repository",
            origin_type=origin_type,
            origin_locator=locator,
            role=role,
            read_scope=read_scope,
        )
        self._ensure_kind_compatibility(round_id, input_id, "repository")
        baseline = self._inspector.inspect(repository_root, include_paths=include_paths)
        revision = {
            "branch": baseline["revision"]["branch"],  # type: ignore[index]
            "commit": baseline["revision"]["commit"],  # type: ignore[index]
            "sha256": baseline["revision"]["sha256"],  # type: ignore[index]
            "observed_at": baseline["revision"]["observed_at"],  # type: ignore[index]
        }
        payload = self._ledger_payload(
            round_id=round_id,
            input_id=input_id,
            kind="repository",
            origin_type=origin_type,
            origin_locator=locator,
            revision=revision,
            read_scope=read_scope,
            role=role,
            repository_baseline=baseline,
        )
        return self._store.append_artifact(
            round_id,
            input_id,
            INPUT_LEDGER_ARTIFACT_KIND,
            payload,
        )

    def create_context_bundle(
        self,
        *,
        round_id: str,
        input_id: str,
        member_input_ids: Sequence[str],
        origin_type: str,
        origin_locator: str,
        role: str = "baseline",
        grouping: str = "user_provided",
    ) -> ArtifactRevision:
        self._validate_common_input(
            round_id=round_id,
            input_id=input_id,
            kind="context_bundle",
            origin_type=origin_type,
            origin_locator=origin_locator,
            role=role,
            read_scope="member artifacts",
        )
        if grouping not in GROUPINGS - {"none"}:
            raise InvalidContextBundleError(f"invalid Context Bundle grouping: {grouping}")
        if isinstance(member_input_ids, str) or not member_input_ids:
            raise InvalidContextBundleError("Context Bundle requires at least one member input id")
        members = tuple(member_input_ids)
        if any(not isinstance(member_id, str) for member_id in members):
            raise InvalidContextBundleError("Context Bundle member ids must be strings")
        if len(set(members)) != len(members):
            raise InvalidContextBundleError("Context Bundle cannot include a duplicate member")
        self._ensure_kind_compatibility(round_id, input_id, "context_bundle")

        member_artifacts: list[ArtifactRevision] = []
        for member_id in members:
            validate_identifier(member_id, "Context Bundle member input_id")
            artifact = self._latest_input_artifact(round_id, member_id)
            if artifact is None:
                raise InvalidContextBundleError(f"Context Bundle member is unknown: {member_id}")
            if artifact.payload["kind"] == "context_bundle":
                raise InvalidContextBundleError("Context Bundles cannot nest another Context Bundle")
            member_artifacts.append(artifact)

        parent_refs = tuple(
            ArtifactRef(round_id, artifact.id, artifact.revision) for artifact in member_artifacts
        )
        member_refs = [reference.to_dict() for reference in parent_refs]
        payload = self._ledger_payload(
            round_id=round_id,
            input_id=input_id,
            kind="context_bundle",
            origin_type=origin_type,
            origin_locator=origin_locator,
            revision={
                "branch": None,
                "commit": None,
                "sha256": sha256(canonical_json_bytes(member_refs)).hexdigest(),
                "observed_at": utc_now(),
            },
            read_scope="member artifacts",
            role=role,
            member_input_ids=list(members),
            grouping=grouping,
            member_refs=member_refs,
        )
        return self._store.append_artifact(
            round_id,
            input_id,
            INPUT_LEDGER_ARTIFACT_KIND,
            payload,
            parent_refs=parent_refs,
        )

    def _validate_common_input(
        self,
        *,
        round_id: str,
        input_id: str,
        kind: str,
        origin_type: str,
        origin_locator: str,
        role: str,
        read_scope: str,
    ) -> None:
        self._store.load_round(round_id)
        validate_identifier(input_id, "input_id")
        if kind not in INPUT_KINDS:
            raise InvalidInputError(f"invalid input kind: {kind}")
        if origin_type not in ORIGIN_TYPES:
            raise InvalidInputError(f"invalid input origin type: {origin_type}")
        if role not in INPUT_ROLES:
            raise InvalidInputError(f"invalid input role: {role}")
        if not isinstance(origin_locator, str) or not origin_locator.strip():
            raise InvalidInputError("input origin locator must be a nonempty string")
        if not isinstance(read_scope, str) or not read_scope.strip():
            raise InvalidInputError("input read_scope must be a nonempty string")

    def _ensure_kind_compatibility(self, round_id: str, input_id: str, kind: str) -> None:
        existing = self._latest_input_artifact(round_id, input_id)
        if existing is not None and existing.payload["kind"] != kind:
            raise InvalidInputError(
                f"input_id {input_id!r} already represents {existing.payload['kind']!r}, not {kind!r}"
            )

    def _latest_input_artifact(
        self,
        round_id: str,
        input_id: str,
    ) -> ArtifactRevision | None:
        artifacts = [
            artifact
            for artifact in self._store.load_round(round_id).artifacts
            if artifact.id == input_id and artifact.kind == INPUT_LEDGER_ARTIFACT_KIND
        ]
        return max(artifacts, key=lambda artifact: artifact.revision, default=None)

    @staticmethod
    def _ledger_payload(
        *,
        round_id: str,
        input_id: str,
        kind: str,
        origin_type: str,
        origin_locator: str,
        revision: dict[str, object],
        read_scope: str,
        role: str,
        member_input_ids: list[str] | None = None,
        grouping: str = "none",
        material: dict[str, str] | None = None,
        repository_baseline: dict[str, object] | None = None,
        member_refs: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": input_id,
            "kind": kind,
            "origin": {"type": origin_type, "locator": origin_locator},
            "revision": revision,
            "read_scope": read_scope,
            "role": role,
            "member_input_ids": member_input_ids or [],
            "grouping": grouping,
            "used_by_rounds": [round_id],
        }
        if material is not None:
            payload["material"] = material
        if repository_baseline is not None:
            payload["repository_baseline"] = repository_baseline
        if member_refs is not None:
            payload["member_refs"] = member_refs
        return payload
