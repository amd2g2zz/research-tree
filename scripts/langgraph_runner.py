"""Optional LangGraph controller for durable research-workflow execution.

The domain DAG remains in ``research_state.json``. LangGraph persists only the
current orchestration turn and delegates every mutation to ``ResearchService``.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Callable

from typing_extensions import NotRequired, TypedDict

from research_service import ResearchService
from research_orchestrator import ResearchOrchestrator


class WorkflowState(TypedDict):
    batch: NotRequired[dict]
    discovery: NotRequired[dict]
    commands: Annotated[list[dict], operator.add]
    results: NotRequired[list[dict]]
    finished: NotRequired[bool]
    task: NotRequired[dict]
    worker_tasks: NotRequired[list[dict]]
    pending_tasks: NotRequired[list[dict]]


def research_graph_config(config: dict | None = None, max_parallel: int | None = None) -> dict:
    """Return an invocation config capped to an explicit worker concurrency.

    LangGraph reads ``max_concurrency`` from the ``configurable`` mapping. The
    caller can impose a smaller cap, but provider discovery concurrency is a
    separate concern managed by ``search_executor``. In particular, do not
    silently reuse ``providers.eligible()["max_parallel"]`` here: a provider
    policy of three must not turn an eight-chapter writer batch into three
    worker slots. When no worker cap is supplied, leave LangGraph's own
    runtime default (or an explicit host value) unchanged.
    """
    result = dict(config or {})
    configurable = dict(result.get("configurable", {}))
    existing = configurable.get("max_concurrency")
    if isinstance(existing, bool) or (existing is not None and (not isinstance(existing, int) or existing < 1)):
        raise ValueError("configurable.max_concurrency must be a positive integer")
    if max_parallel is not None:
        if isinstance(max_parallel, bool) or not isinstance(max_parallel, int) or max_parallel < 1:
            raise ValueError("max_parallel must be a positive integer")
        configurable["max_concurrency"] = min(existing, max_parallel) if existing is not None else max_parallel
    result["configurable"] = configurable
    return result


def invoke_research_graph(graph: Any, value: dict, config: dict | None = None,
                          max_parallel: int | None = None):
    """Invoke a compiled research graph with an optional worker concurrency cap."""
    return graph.invoke(value, research_graph_config(config, max_parallel))


def build_research_graph(checkpointer: Any, service: ResearchService | None = None,
                         worker_executor: Callable[[dict], dict | list[dict]] | None = None):
    """Build a resumable controller around a persistent LangGraph checkpointer.

    The caller supplies durable storage in production. ``InMemorySaver`` is
    intentionally not chosen here because it cannot resume a process restart.
    """
    if checkpointer is None:
        raise ValueError("a persistent LangGraph checkpointer is required")
    try:
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import Send
        from langgraph.types import interrupt
    except ImportError as exc:
        raise RuntimeError("LangGraph is not installed; run `uv sync`") from exc

    worker = service or ResearchService()
    coordinator = ResearchOrchestrator(worker)

    def discover(_: WorkflowState) -> dict:
        # Coordinator collection is deliberately completed before the task
        # batch is read. This node never turns a pre-search formulation task
        # into a worker; only post-collection review/extraction tasks fan out.
        return {"discovery": coordinator.discover(), "batch": coordinator.plan()}

    def request(state: WorkflowState) -> dict:
        commands = interrupt({"kind": "research_worker_batch", "batch": state["batch"]})
        if not isinstance(commands, list):
            raise ValueError("workflow resume value must be a list of worker commands")
        return {"commands": commands}

    def apply(state: WorkflowState) -> dict:
        results = worker.execute_batch(state["commands"])
        return {"results": results, "finished": any(item.get("operation") == "freeze" for item in state["commands"])}

    def after_discover(state: WorkflowState):
        return "request" if state["batch"].get("tasks") else END

    def after_apply(_: WorkflowState):
        # End this orchestration turn. A later host turn starts the next
        # coordinator stage, avoiding an unbounded self-scheduling loop.
        return END

    if worker_executor:
        def after_worker_discover(state: WorkflowState):
            return "prepare_workers" if state["batch"].get("tasks") else END

        def prepare_workers(state: WorkflowState) -> dict:
            remaining = state.get("pending_tasks")
            if remaining is None:
                remaining = list(state["batch"]["tasks"])
            if not isinstance(remaining, list) or not all(isinstance(item, dict) for item in remaining):
                raise ValueError("worker batch tasks must be objects")
            maximum = state["batch"].get("max_parallel", 1)
            if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
                raise ValueError("worker batch max_parallel must be a positive integer")
            return {"worker_tasks": remaining[:maximum], "pending_tasks": remaining[maximum:]}

        def dispatch(state: WorkflowState):
            return [Send("worker", {"task": task}) for task in state.get("worker_tasks", [])]

        def run_worker(state: WorkflowState) -> dict:
            commands = worker_executor(state["task"])
            if isinstance(commands, dict):
                commands = [commands]
            if not isinstance(commands, list) or not all(isinstance(item, dict) for item in commands):
                raise ValueError("worker executor must return one command or a list of commands")
            return {"commands": commands}

        def after_collect(state: WorkflowState):
            return "prepare_workers" if state.get("pending_tasks") else "apply"

        graph = StateGraph(WorkflowState)
        graph.add_node("discover", discover)
        graph.add_node("prepare_workers", prepare_workers)
        graph.add_node("worker", run_worker)
        graph.add_node("collect", lambda _: {})
        graph.add_node("apply", apply)
        graph.add_edge(START, "discover")
        graph.add_conditional_edges("discover", after_worker_discover, ["prepare_workers", END])
        graph.add_conditional_edges("prepare_workers", dispatch, ["worker"])
        graph.add_edge("worker", "collect")
        graph.add_conditional_edges("collect", after_collect, ["prepare_workers", "apply"])
        graph.add_edge("apply", END)
        return graph.compile(checkpointer=checkpointer)

    graph = StateGraph(WorkflowState)
    graph.add_node("discover", discover)
    graph.add_node("request", request)
    graph.add_node("apply", apply)
    graph.add_edge(START, "discover")
    graph.add_conditional_edges("discover", after_discover, ["request", END])
    graph.add_edge("request", "apply")
    graph.add_conditional_edges("apply", after_apply, [END])
    return graph.compile(checkpointer=checkpointer)
