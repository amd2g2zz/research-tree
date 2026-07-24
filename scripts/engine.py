"""research-tree core engine — the mechanical algorithm.

This module IS the algorithm. Everything deterministic about
"recursive-descent + DAG" lives here:

  * the DAG itself (networkx.DiGraph) with weighted, cycle-safe edges
  * weighted PageRank (in-process, no scipy)  ->  per-node importance
    (high in-degree from important parents == cross-cutting sub-problem)
  * community detection + centroid extraction ->  the "real" questions
  * lexical proximity to the (vague) root phrase ->  loose relevance anchor
  * double-low pruning, per-node backtrack budgets, convergence detection
  * a phase machine (seed -> grow -> resolve -> converged)
  * `next()`: the one mechanical decision function that tells the caller
    (the LLM, via the CLI) exactly which judgment to perform next

The LLM never decides priority. It only fills three judgment slots the engine
asks for: formulate queries, propose growth (sub-questions/edges), synthesise
an answer. Search dispatch (anysearch + ddg) is a sibling script.

CLI surface (each maps 1:1 to an algorithm step):
  init / next / grow / formulate / search-result / resolve / backtrack
  / reweight / reframe / status / export

State is a single dag.json under <workspace>/research_drift/; every action
appends a record to drift_log.jsonl (the descent trajectory).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import networkx as nx

try:
    from networkx.algorithms.community import louvain_communities
except Exception:  # pragma: no cover - fallback path
    louvain_communities = None


# ---------------------------------------------------------------------------
# Config (mechanical knobs; overridable at init)
# ---------------------------------------------------------------------------

DEFAULTS = {
    "max_depth": 4,            # recursion bound
    "max_retries": 2,          # backtrack budget per node
    "pr_alpha": 0.85,          # PageRank damping
    "pr_epsilon": 0.02,        # L1 delta below this == "stable" for one round
    "pr_stable_rounds": 2,     # consecutive stable growth rounds to converge
    "grow_step_budget": 30,    # growth steps before forcing resolve phase
    "lateral_every": 5,        # emit a lateral query every N steps (>=2 centroids)
    "top_centroids_k": 5,
    "merge_threshold": 0.6,    # lexical Jaccard above this reuses an existing node
    "prune_weight": 0.05,      # prune if pagerank < this AND ...
    "prune_proximity": 0.10,   # ... root proximity < this (double-low rule)
    "synthesize_threshold": 0.6,
}

# Node lifecycle states.
OPEN, QUERYING, GROWING, SYNTHESIZED, FAILED, PRUNED = (
    "open", "querying", "growing", "synthesized", "failed", "pruned",
)
UNRESOLVED = {OPEN, QUERYING, GROWING}


# ---------------------------------------------------------------------------
# Paths & small helpers
# ---------------------------------------------------------------------------

def workspace() -> str:
    return os.environ.get("RESEARCH_WORKSPACE", os.getcwd())


def drift_dir() -> str:
    return os.path.join(workspace(), "research_drift")


def dag_path() -> str:
    return os.path.join(drift_dir(), "dag.json")


def drift_log_path() -> str:
    return os.path.join(drift_dir(), "drift_log.jsonl")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tokens(text: str) -> set:
    import re
    return {w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower())}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Engine:
    def __init__(self, graph: nx.DiGraph, meta: dict):
        self.G = graph
        self.meta = meta
        self._dirty = True  # PR/community need recompute

    # -- persistence --------------------------------------------------------

    @classmethod
    def load(cls) -> "Engine":
        path = dag_path()
        if not os.path.exists(path):
            sys.exit(f"no dag at {path} - run `engine init` first")
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        G = nx.DiGraph()
        for nid, attrs in data.get("nodes", {}).items():
            G.add_node(nid, **attrs)
        for e in data.get("edges", []):
            u, v, w = e[0], e[1], e[2] if len(e) > 2 else 1.0
            G.add_edge(u, v, weight=float(w))
        meta = {k: v for k, v in data.items() if k not in ("nodes", "edges")}
        meta.setdefault("config", dict(DEFAULTS))
        return cls(G, meta)

    def save(self) -> None:
        os.makedirs(drift_dir(), exist_ok=True)
        data = dict(self.meta)
        data["nodes"] = {n: dict(d) for n, d in self.G.nodes(data=True)}
        data["edges"] = [[u, v, d.get("weight", 1.0)] for u, v, d in self.G.edges(data=True)]
        with open(dag_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)

    def log(self, action: str, payload: dict) -> None:
        os.makedirs(drift_dir(), exist_ok=True)
        rec = {"step": self.meta.get("step", 0), "action": action, "ts": now_iso()}
        rec.update(payload)
        with open(drift_log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # -- graph ops ----------------------------------------------------------

    def _new_id(self, prefix: str = "n") -> str:
        import hashlib
        seq = self.meta.get("seq", 0) + 1
        self.meta["seq"] = seq
        h = hashlib.sha1(f"{seq}-{now_iso()}".encode()).hexdigest()[:6]
        return f"{prefix}_{seq:03d}_{h}"

    def find_similar(self, question: str, exclude: str | None = None) -> str | None:
        """Lexical memoisation: return an existing equivalent node if any."""
        qt = _tokens(question)
        if not qt:
            return None
        cfg = self.meta["config"]
        best, best_s = None, 0.0
        for n, d in self.G.nodes(data=True):
            if n == exclude or d.get("state") == PRUNED:
                continue
            s = _jaccard(qt, _tokens(d.get("question", "")))
            if s > best_s:
                best, best_s = n, s
        return best if best_s >= cfg["merge_threshold"] else None

    def _would_cycle(self, u: str, v: str) -> bool:
        if u == v:
            return True
        # adding u->v cycles iff v can already reach u
        return nx.has_path(self.G, v, u)

    def add_edge_safe(self, u: str, v: str, weight: float) -> bool:
        if self._would_cycle(u, v):
            return False
        if self.G.has_edge(u, v):
            cur = self.G[u][v].get("weight", 0.0)  # keep the stronger witness
            self.G[u][v]["weight"] = max(cur, float(weight))
        else:
            self.G.add_edge(u, v, weight=float(weight))
        return True

    def add_node(self, question: str, kind: str, parent: str | None,
                 weight: float = 0.8, depth: int | None = None) -> str:
        """Create a node or reuse an equivalent one (DAG memoisation).

        Returns the node id used (new or reused). Cross-links to existing
        nodes are what turn the tree into a DAG and surface cross-cutting
        sub-problems as high-in-degree nodes.
        """
        reuse = self.find_similar(question)
        nid = reuse or self._new_id()
        if not reuse:
            d = 0 if parent is None else (
                depth if depth is not None else self.G.nodes[parent].get("depth", 0) + 1
            )
            self.G.add_node(nid, id=nid, question=question, kind=kind, state=OPEN,
                            answer=None, confidence=0.0, pagerank=0.0,
                            community=None, is_centroid=False, depth=d,
                            queries=[], evidence=[], retries=0,
                            created_step=self.meta.get("step", 0), resolved_step=None)
        if parent is not None:
            self.add_edge_safe(parent, nid, weight)
        self._dirty = True
        return nid

    # -- scoring: PageRank, communities, centroids, proximity, prune --------

    def _weighted_pagerank(self, alive, alpha=0.85, tol=1e-6, max_iter=300):
        """In-process weighted PageRank (power iteration) — no scipy dependency.

        High in-degree from important parents == cross-cutting sub-problem.
        Dangling nodes (no out-edges) redistribute their mass uniformly.
        """
        n_alive = len(alive)
        if n_alive == 0:
            return {}
        outw = {n: 0.0 for n in alive}
        succ = {n: [] for n in alive}
        for u, v, d in self.G.edges(data=True):
            if u in outw and v in outw:
                w = float(d.get("weight", 1.0))
                outw[u] += w
                succ[u].append((v, w))
        rank = {n: 1.0 / n_alive for n in alive}
        base = (1 - alpha) / n_alive
        for _ in range(max_iter):
            new = {n: base for n in alive}
            dangling = alpha * sum(rank[n] for n in alive if outw[n] == 0) / n_alive
            for n in alive:
                new[n] += dangling
            for u in alive:
                if outw[u] > 0:
                    share = alpha * rank[u]
                    for v, w in succ[u]:
                        new[v] += share * (w / outw[u])
            delta = sum(abs(new[n] - rank[n]) for n in alive)
            rank = new
            if delta < tol:
                break
        return rank

    def recompute(self) -> None:
        cfg = self.meta["config"]
        alive = [n for n, d in self.G.nodes(data=True) if d.get("state") != PRUNED]
        pr = self._weighted_pagerank(alive, cfg["pr_alpha"])
        # communities on the undirected projection (related sub-problem clusters)
        comms = []
        if len(alive) >= 2:
            ug = nx.Graph(self.G.subgraph(alive))
            try:
                comms = (louvain_communities(ug) if louvain_communities
                         else nx.algorithms.community.greedy_modularity_communities(ug))
            except Exception:
                comms = []
        comm_of, centroids = {}, set()
        for i, c in enumerate(comms):
            members = [n for n in c if n in pr]
            if not members:
                continue
            cent = max(members, key=lambda n: pr[n])
            for n in members:
                comm_of[n] = i
            centroids.add(cent)
        root_toks = _tokens(self.meta.get("root_phrase", ""))
        for n, d in self.G.nodes(data=True):
            d["pagerank"] = round(pr.get(n, 0.0), 6)
            d["community"] = comm_of.get(n)
            d["is_centroid"] = n in centroids
            d["root_proximity"] = round(_jaccard(_tokens(d.get("question", "")), root_toks), 4)
        # double-low prune (low weight AND low proximity)
        for n, d in self.G.nodes(data=True):
            if (d.get("state") in UNRESOLVED and n != self.meta.get("root")
                    and d["pagerank"] < cfg["prune_weight"]
                    and d["root_proximity"] < cfg["prune_proximity"]):
                d["state"] = PRUNED
        # convergence: PageRank stability, measured ONLY across a real growth
        # round. A no-op recompute must not register a spurious "stable" round.
        prev = self.meta.get("prev_pagerank", {})
        delta = sum(abs(pr.get(n, 0.0) - prev.get(n, 0.0)) for n in pr) if prev else 1.0
        if self.meta.get("grew_since_recompute"):
            self.meta["grew_since_recompute"] = False
            if prev and delta < cfg["pr_epsilon"]:
                self.meta["pr_stable_count"] = self.meta.get("pr_stable_count", 0) + 1
            else:
                self.meta["pr_stable_count"] = 0
        self.meta["prev_pagerank"] = {n: pr.get(n, 0.0) for n in pr}
        self.meta["pr_delta"] = round(delta, 6)
        self._dirty = False

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.recompute()

    # -- phase machine ------------------------------------------------------

    def _advance_phase(self) -> None:
        cfg = self.meta["config"]
        phase = self.meta.get("phase", "seed")
        root = self.meta.get("root")
        if root is None:
            return
        if phase == "seed" and self.G.out_degree(root) > 0:
            self.meta["phase"] = "grow"
            self.meta["grow_steps"] = 0
            self.meta["needs_reframe"] = True
            self.log("phase", {"from": "seed", "to": "grow"})
            phase = "grow"
        if phase == "grow":
            done_growing = (self.meta.get("grow_steps", 0) >= cfg["grow_step_budget"]
                            or self.meta.get("pr_stable_count", 0) >= 1)
            if done_growing:
                self.meta["phase"] = "resolve"
                self.meta["needs_reframe"] = True
                self.log("phase", {"from": "grow", "to": "resolve"})
                phase = "resolve"
        if phase == "resolve":
            centroids = self._centroids()
            centroids_done = all(
                self.G.nodes[c].get("state") == SYNTHESIZED for c in centroids)
            if (centroids and centroids_done
                    and self.meta.get("pr_stable_count", 0) >= cfg["pr_stable_rounds"]):
                self.meta["phase"] = "converged"
                self.log("phase", {"from": "resolve", "to": "converged"})

    def _centroids(self) -> list:
        return [n for n, d in self.G.nodes(data=True)
                if d.get("is_centroid") and d.get("state") != PRUNED]

    # -- the one mechanical decision function -------------------------------

    def next(self) -> dict:
        self.ensure_fresh()
        self._advance_phase()
        cfg = self.meta["config"]
        phase = self.meta.get("phase", "seed")
        root = self.meta.get("root")

        if phase == "converged":
            return {"action": "done", "phase": phase,
                    "reason": "PageRank stable + centroids resolved"}

        if self.meta.get("needs_reframe"):
            self.meta["needs_reframe"] = False
            return {"action": "reframe", "phase": phase,
                    "centroids": self._centroid_briefs(),
                    "reason": "structure emerged - sharpen the research frame"}

        # lateral intersection queries between top centroids (cheap cross-cut)
        step = self.meta.get("step", 0)
        if (phase in ("grow", "resolve") and step > 0
                and step % cfg["lateral_every"] == 0
                and len(self._centroids()) >= 2):
            c = self._centroids()[:2]
            return {"action": "lateral", "phase": phase, "pair": c,
                    "pair_questions": [self.G.nodes[k]["question"] for k in c],
                    "reason": "probe the intersection of two central sub-problems"}

        if (root is not None and self.G.nodes[root].get("state") in UNRESOLVED
                and self.G.out_degree(root) == 0):
            return {"action": "decompose", "node": root, "phase": phase,
                    "reason": "seed: decompose the (vague) root into sub-questions"}

        target = self._pick_target()
        if target is None:
            return {"action": "done", "phase": phase,
                    "reason": "no unresolved nodes remain"}
        return self._action_for(target, phase)

    def _pick_target(self) -> str | None:
        """Highest-PageRank unresolved, non-pruned node (tie-break: shallowest)."""
        cand = [(d["pagerank"], -d.get("depth", 0), n)
                for n, d in self.G.nodes(data=True)
                if d.get("state") in UNRESOLVED and n != self.meta.get("root")]
        if not cand:
            return None
        cand.sort(reverse=True)
        return cand[0][2]

    def _action_for(self, n: str, phase: str) -> dict:
        d = self.G.nodes[n]
        kind = d.get("kind", "terminal")
        base = {"node": n, "phase": phase, "question": d["question"],
                "pagerank": d["pagerank"], "depth": d.get("depth", 0)}
        if kind == "terminal":
            if not d.get("queries"):
                return {**base, "action": "formulate",
                        "reason": "terminal needs search queries"}
            if not d.get("answer"):
                return {**base, "action": "synthesize",
                        "reason": "terminal has evidence - answer it"}
            return {**base, "action": "synthesize"}
        # non-terminal
        children = list(self.G.successors(n))
        unresolved_children = [c for c in children
                               if self.G.nodes[c].get("state") in UNRESOLVED]
        if not children and d.get("depth", 0) < self.meta["config"]["max_depth"]:
            return {**base, "action": "decompose",
                    "reason": "non-terminal has no children - descend"}
        if unresolved_children:
            # descend: next() re-picks the highest-PR child automatically;
            # tell the caller synthesis is blocked on children.
            return {**base, "action": "await_children",
                    "blocked_on": unresolved_children,
                    "reason": "descend into unresolved children first"}
        if d.get("answer") is None:
            return {**base, "action": "synthesize",
                    "reason": "all children resolved - synthesise"}
        return {**base, "action": "synthesize"}

    def _centroid_briefs(self) -> list:
        out = []
        for n, d in self.G.nodes(data=True):
            if d.get("is_centroid") and d.get("state") != PRUNED:
                out.append({"node": n, "question": d["question"],
                            "pagerank": d["pagerank"],
                            "state": d.get("state"),
                            "community": d.get("community")})
        out.sort(key=lambda x: x["pagerank"], reverse=True)
        return out[: self.meta["config"]["top_centroids_k"]]

    # -- mutations the LLM calls after performing judgment ------------------

    def grow(self, parent: str, proposals: list, cross_edges: list | None = None) -> dict:
        """Merge LLM-proposed sub-questions into the DAG.

        proposals: [{question, kind, weight}]  (kind in terminal|nonterminal)
        cross_edges: [{v, weight}] explicit links from `parent` to existing nodes
        Returns counts + ids; reused == cross-cutting sub-problems surfaced.
        """
        self.meta["step"] = self.meta.get("step", 0) + 1
        if self.meta.get("phase") == "grow":
            self.meta["grow_steps"] = self.meta.get("grow_steps", 0) + 1
        created, reused = [], []
        for p in proposals:
            q = p.get("question", "").strip()
            if not q:
                continue
            before = set(self.G.nodes)
            nid = self.add_node(q, p.get("kind", "terminal"), parent,
                                weight=float(p.get("weight", 0.8)))
            if nid not in before:
                created.append(nid)
            elif nid not in created:
                reused.append(nid)  # linked to a pre-existing node = cross-cut
        for ce in (cross_edges or []):
            v = ce.get("v")
            if v in self.G and v != parent:
                self.add_edge_safe(parent, v, float(ce.get("weight", 0.5)))
                if v not in reused and v not in created:
                    reused.append(v)
        if proposals or cross_edges:
            self.meta["grew_since_recompute"] = True
        self.log("grow", {"parent": parent, "created": created, "reused": reused,
                          "cross_edges": cross_edges or []})
        self.save()
        return {"created": created, "reused": reused,
                "note": "reused == cross-cutting sub-problems linked, not duplicated"}

    def formulate(self, node: str, queries: list) -> dict:
        self.G.nodes[node]["queries"] = queries
        self.G.nodes[node]["state"] = QUERYING
        self.meta["step"] = self.meta.get("step", 0) + 1
        self.log("formulate", {"node": node, "queries": queries})
        self.save()
        return {"node": node, "queries": queries}

    def search_result(self, node: str, evidence: list) -> dict:
        """Store evidence refs/hits produced by search_dispatch (judgment-free)."""
        cur = self.G.nodes[node].setdefault("evidence", [])
        cur.extend(evidence)
        self.log("search_result", {"node": node, "added": len(evidence)})
        self.save()
        return {"node": node, "evidence_count": len(cur)}

    def resolve(self, node: str, answer: str, confidence: float) -> dict:
        d = self.G.nodes[node]
        d["answer"] = answer
        d["confidence"] = float(confidence)
        d["resolved_step"] = self.meta.get("step", 0)
        cfg = self.meta["config"]
        if confidence < cfg["synthesize_threshold"] and d.get("retries", 0) < cfg["max_retries"]:
            d["state"] = OPEN  # stays unresolved -> next() will backtrack
            d["retries"] = d.get("retries", 0) + 1
            outcome = "low_confidence_backtrack"
        else:
            d["state"] = SYNTHESIZED if confidence >= cfg["synthesize_threshold"] else FAILED
            outcome = d["state"]
        self.meta["step"] = self.meta.get("step", 0) + 1
        self.log("resolve", {"node": node, "confidence": confidence, "outcome": outcome})
        self.save()
        return {"node": node, "state": d["state"], "outcome": outcome}

    def backtrack(self, node: str, new_kind: str | None = None) -> dict:
        d = self.G.nodes[node]
        d["retries"] = d.get("retries", 0) + 1
        d["state"] = OPEN
        d["answer"] = None
        d["confidence"] = 0.0
        if new_kind:
            d["kind"] = new_kind  # e.g. retry a terminal as nonterminal
        if d["retries"] > self.meta["config"]["max_retries"]:
            d["state"] = FAILED
        self.meta["step"] = self.meta.get("step", 0) + 1
        self.log("backtrack", {"node": node, "retries": d["retries"], "state": d["state"]})
        self.save()
        return {"node": node, "state": d["state"], "retries": d["retries"]}

    def reframe(self, frame: str) -> dict:
        self.meta["research_frame"] = frame
        os.makedirs(drift_dir(), exist_ok=True)
        with open(os.path.join(drift_dir(), "frame.md"), "w", encoding="utf-8") as fh:
            fh.write(frame)
        self.log("reframe", {"frame_len": len(frame)})
        self.save()
        return {"centroids": self._centroid_briefs()}

    # -- status -------------------------------------------------------------

    def status(self) -> dict:
        self.ensure_fresh()
        self._advance_phase()
        states = {}
        for _, d in self.G.nodes(data=True):
            states[d.get("state")] = states.get(d.get("state"), 0) + 1
        return {
            "phase": self.meta.get("phase"),
            "step": self.meta.get("step", 0),
            "pr_stable_count": self.meta.get("pr_stable_count", 0),
            "pr_delta": self.meta.get("pr_delta"),
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "state_counts": states,
            "top_centroids": self._centroid_briefs(),
            "unresolved": [n for n, d in self.G.nodes(data=True)
                           if d.get("state") in UNRESOLVED],
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _init(args) -> None:
    cfg = dict(DEFAULTS)
    for kv in args.config or []:
        k, _, v = kv.partition("=")
        if k in cfg:
            cur = cfg[k]
            cfg[k] = type(cur)(v) if not isinstance(cur, bool) else (v == "true")
    os.makedirs(drift_dir(), exist_ok=True)
    G = nx.DiGraph()
    meta = {"phase": "seed", "step": 0, "seq": 0, "config": cfg,
            "root_phrase": args.question, "pr_stable_count": 0}
    eng = Engine(G, meta)
    rid = eng.add_node(args.question, "nonterminal", parent=None)
    meta["root"] = rid
    eng.log("init", {"root": rid, "question": args.question})
    eng.save()
    print(json.dumps({"root": rid, "phase": "seed",
                      "dag": dag_path()}, ensure_ascii=False, indent=2))


def _with_engine(fn):
    def wrap(args):
        fn(Engine.load(), args)
    return wrap


def _next(eng: Engine, args):
    print(json.dumps(eng.next(), ensure_ascii=False, indent=2))


def _grow(eng: Engine, args):
    proposals = json.loads(args.nodes) if args.nodes else []
    cross = json.loads(args.cross) if args.cross else []
    print(json.dumps(eng.grow(args.parent, proposals, cross),
                     ensure_ascii=False, indent=2))


def _formulate(eng: Engine, args):
    print(json.dumps(eng.formulate(args.node, json.loads(args.queries)),
                     ensure_ascii=False, indent=2))


def _search_result(eng: Engine, args):
    print(json.dumps(eng.search_result(args.node, json.loads(args.evidence)),
                     ensure_ascii=False, indent=2))


def _resolve(eng: Engine, args):
    print(json.dumps(eng.resolve(args.node, args.answer, args.confidence),
                     ensure_ascii=False, indent=2))


def _backtrack(eng: Engine, args):
    print(json.dumps(eng.backtrack(args.node, args.new_kind),
                     ensure_ascii=False, indent=2))


def _reweight(eng: Engine, args):
    eng.recompute()
    eng.save()
    print(json.dumps({"pr_delta": eng.meta.get("pr_delta"),
                      "pr_stable_count": eng.meta.get("pr_stable_count", 0)},
                     ensure_ascii=False, indent=2))


def _reframe(eng: Engine, args):
    print(json.dumps(eng.reframe(args.frame), ensure_ascii=False, indent=2))


def _status(eng: Engine, args):
    print(json.dumps(eng.status(), ensure_ascii=False, indent=2))


def _export(eng: Engine, args):
    s = eng.status()
    if args.format == "json":
        data = {"meta": {k: v for k, v in eng.meta.items() if k != "prev_pagerank"},
                "nodes": {n: dict(d) for n, d in eng.G.nodes(data=True)},
                "edges": [[u, v, d.get("weight")] for u, v, d in eng.G.edges(data=True)]}
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    lines = ["# research-tree DAG",
             f"phase: {s['phase']} | step: {s['step']} | "
             f"nodes: {s['nodes']} | edges: {s['edges']}", ""]
    root = eng.meta.get("root")
    seen = set()

    def walk(n, depth):
        if n in seen:
            return
        seen.add(n)
        d = eng.G.nodes[n]
        mark = "*" if d.get("is_centroid") else "-"
        conf = f" conf={d['confidence']:.2f}" if d.get("confidence") else ""
        lines.append(f"{'  ' * depth}- {mark} [{d.get('state')[:4]}] "
                     f"pr={d['pagerank']:.3f}{conf} {d['question']}")
        for c in eng.G.successors(n):
            walk(c, depth + 1)

    if root:
        walk(root, 0)
    for n, d in eng.G.nodes(data=True):
        if n not in seen:
            lines.append(f"- [orphan:{d.get('state')[:4]}] pr={d['pagerank']:.3f} "
                         f"{d['question']}  <!-- parents={list(eng.G.predecessors(n))} -->")
    print("\n".join(lines))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="engine", description="research-tree core engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="seed a new DAG from a (vague) root question")
    i.add_argument("--question", required=True)
    i.add_argument("--config", nargs="*", help="key=value overrides, e.g. max_depth=5")
    i.set_defaults(func=_init)

    n = sub.add_parser("next", help="the one mechanical decision: what to do next")
    n.set_defaults(func=_with_engine(_next))

    g = sub.add_parser("grow", help="merge LLM-proposed sub-questions under a parent")
    g.add_argument("--parent", required=True)
    g.add_argument("--nodes", required=True, help='JSON: [{"question","kind","weight"}]')
    g.add_argument("--cross", help='JSON: [{"v","weight"}] explicit cross-links')
    g.set_defaults(func=_with_engine(_grow))

    f = sub.add_parser("formulate", help="store search queries for a terminal")
    f.add_argument("--node", required=True)
    f.add_argument("--queries", required=True, help="JSON list of query strings")
    f.set_defaults(func=_with_engine(_formulate))

    sr = sub.add_parser("search-result", help="store evidence produced by search_dispatch")
    sr.add_argument("--node", required=True)
    sr.add_argument("--evidence", required=True, help="JSON list of evidence refs/hits")
    sr.set_defaults(func=_with_engine(_search_result))

    r = sub.add_parser("resolve", help="record an answer + confidence for a node")
    r.add_argument("--node", required=True)
    r.add_argument("--answer", required=True)
    r.add_argument("--confidence", type=float, required=True)
    r.set_defaults(func=_with_engine(_resolve))

    b = sub.add_parser("backtrack", help="reset a node for retry (within budget)")
    b.add_argument("--node", required=True)
    b.add_argument("--new-kind", choices=["terminal", "nonterminal"])
    b.set_defaults(func=_with_engine(_backtrack))

    rw = sub.add_parser("reweight", help="recompute PageRank/communities/centroids/prune")
    rw.set_defaults(func=_with_engine(_reweight))

    rf = sub.add_parser("reframe", help="store the sharpened research frame")
    rf.add_argument("--frame", required=True)
    rf.set_defaults(func=_with_engine(_reframe))

    st = sub.add_parser("status", help="graph + convergence summary")
    st.set_defaults(func=_with_engine(_status))

    ex = sub.add_parser("export", help="dump dag.json or a markdown outline")
    ex.add_argument("--format", choices=["json", "md"], default="md")
    ex.set_defaults(func=_with_engine(_export))

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
