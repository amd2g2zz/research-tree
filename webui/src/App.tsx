/** research-tree WebUI — ChatGPT-style layout (issue #653, user ruling
 * 2026-11-03: 按 ChatGPT 的页面做).

- **Left sidebar** (260px): 「新研究」 button; project→task list; settings +
  pi readiness at the bottom.
- **Main column** = the chat hub is THE product surface: centered stream
  (user bubbles right, rt receipts full-width left), sticky composer pill
  that spans all phases (追加信息门).
- **Right canvas panel** slides out from the header (分解 / 研究 / 版本) —
  like ChatGPT's canvas, the chat never leaves.
- **Settings** = a modal over everything; pi's config stays the single
  source (#638), keys never echo.
*/

import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

type Panel = null | "decomp" | "research" | "versions";

interface ProjectCard {
  project_id: string;
  name: string;
  description: string;
  status: string;
  attachments: Array<{ id: string; kind: string; label: string }>;
}
interface VersionNode {
  v: number;
  verdict: string;
  commit_hash: string;
  summary: string;
  forked: boolean;
}
interface TreeNode extends ProjectCard {
  vitals: { research_lines: number; latest: { v: number; verdict: string; commit_hash: string } | null; elapsed_ms: number };
  lines: Array<{
    task_id: string;
    role: "main" | "fork";
    latest: { v: number; verdict: string; commit_hash: string; summary: string } | null;
    versions: VersionNode[];
    draft: { base_v: number | null; updated_at: string } | null;
  }>;
}
interface ChatMessage {
  seq: number;
  role: "user" | "rt" | "system";
  kind: string;
  text: string;
  receipt_json: string | null;
  created_at: string;
}
interface TaskStatus {
  phase: string;
  latest: { v: number; verdict: string; commit_hash: string } | null;
  routed_count: number;
}
type UtteranceKind = "auto" | "preference" | "claim" | "guess" | "branch";
interface PiModelInfo {
  id: string;
  name: string;
  provider: string;
}
interface PiConfig {
  present: boolean;
  default_model: string | null;
  models: PiModelInfo[];
  auth_providers: string[];
  providers: string[];
  config_path: string;
  keyed_session_ready: boolean;
  readiness: { has_provider_key: boolean; has_model: boolean; has_default_model: boolean };
  follows_pi_default: boolean;
  default_extensions?: Array<{ name: string; installed: boolean }>;
}
interface LogLine {
  kind: "engine" | "rpc" | "error";
  text: string;
}
interface ClassificationBadge {
  classified_by?: string;
  routed?: string;
}

const KIND_LABELS: Record<UtteranceKind, string> = {
  auto: "自动",
  preference: "偏好",
  claim: "主张",
  guess: "猜测",
  branch: "岔路",
};
const CLASSIFIED_BY_LABELS: Record<string, string> = {
  user: "手动",
  "pi-session": "pi 会话",
  heuristic: "规则回退",
};
const ELEMENT_META: Array<[string, string]> = [
  ["requirements", "🎯 需求"],
  ["constraints", "📌 条件约束"],
  ["background", "📖 任务背景"],
  ["intents", "💡 用户意图"],
  ["refusals", "🚫 拒绝点"],
  ["difficulties", "⚠ 难点→kill 候选"],
];

export function App() {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [piConfig, setPiConfig] = useState<PiConfig | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  // UI chrome
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [panel, setPanel] = useState<Panel>(null);
  const [modal, setModal] = useState<null | "settings" | "new" | "snapshot">(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);
  // hub
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<UtteranceKind>("auto");
  const [thinking, setThinking] = useState(false);
  // decomp
  const [decomp, setDecomp] = useState<{
    decomposition_id: string;
    elements: Record<string, Array<Record<string, unknown>>>;
    checklist: { complete: boolean; gaps: string[] };
    status?: string;
  } | null>(null);
  // research
  const [research, setResearch] = useState<{
    question: { task_id: string; title: string };
    claims: Record<string, { text: string; posterior: number; verify_tier: string; weight: string; state: string }>;
    stages: Array<{ stage_id: string; title: string; status: string; claim_ids: string[]; depends_on: string[] }>;
    transitions: Array<{ from: string | null; to: string }>;
    providers: string[];
  } | null>(null);
  const [beats, setBeats] = useState<Array<{ seq: number; event_type: string; summary: string }>>([]);
  const [beat, setBeat] = useState<number | null>(null);
  const [atView, setAtView] = useState<{ console: string[]; claims: Record<string, Record<string, unknown>> } | null>(null);
  const [drawer, setDrawer] = useState<{ claimId: string; lineage: { steps: Array<{ layer: string; detail?: string }>; raw_evidence?: string } | null } | null>(null);
  // versions
  const [vtl, setVtl] = useState<{
    is_main_branch: boolean;
    versions: VersionNode[];
    draft: { base_v: number | null; updated_at: string } | null;
    fork_parent: { task_id: string; v: number } | null;
  } | null>(null);
  const [snap, setSnap] = useState<{ banner: { v: number; commit_hash: string; verdict: string; summary: string }; report: Record<string, unknown> } | null>(null);
  // settings
  const [settings, setSettings] = useState<PiConfig | null>(null);
  const [provider, setProvider] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [modelId, setModelId] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [newName, setNewName] = useState("");

  const push = useCallback((kindLog: LogLine["kind"], text: string) => {
    setLog((prev) => [...prev.slice(-199), { kind: kindLog, text }]);
  }, []);

  const connect = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => resolve(ws);
      ws.onerror = reject;
    });
  }, []);

  const getSocket = useCallback(async (): Promise<WebSocket> => {
    if (socketRef.current === null || socketRef.current.readyState > 1) {
      socketRef.current = await connect();
    }
    return socketRef.current;
  }, [connect]);

  const rpc = useCallback(
    (ws: WebSocket, method: string, params: Record<string, unknown> = {}) => {
      return new Promise<Record<string, unknown>>((resolve, reject) => {
        const id = Date.now() + Math.random();
        const onMessage = (ev: MessageEvent): void => {
          const msg = JSON.parse(String(ev.data)) as Record<string, unknown>;
          if (msg.id === id) {
            ws.removeEventListener("message", onMessage);
            if (msg.ok === true) {
              resolve(msg.result as Record<string, unknown>);
            } else {
              reject(new Error(String(msg.error)));
            }
          } else if (msg.event === "engine") {
            const line = msg.line as { event_type?: string; seq?: number };
            push("engine", `#${line.seq} ${line.event_type}`);
          }
        };
        ws.addEventListener("message", onMessage);
        ws.send(JSON.stringify({ id, method, params }));
      });
    },
    [push],
  );

  const refreshTree = useCallback(async () => {
    const projects = ((await (await fetch("/api/tree")).json()) as { projects: TreeNode[] }).projects;
    setTree(projects);
    setActiveTaskId((current) => {
      if (current !== null) {
        return current;
      }
      const active = projects.find((p) => p.status === "active");
      return active?.lines.find((l) => l.role === "main")?.task_id ?? null;
    });
  }, []);

  useEffect(() => {
    void refreshTree();
    void fetch("/api/config/pi")
      .then((r) => r.json())
      .then((c) => setPiConfig(c as never));
  }, [refreshTree]);

  // ------------- derived selection -------------
  const activeProject = tree.find((p) => p.lines.some((l) => l.task_id === activeTaskId)) ?? null;
  const activeTask = activeProject?.lines.find((l) => l.task_id === activeTaskId) ?? null;
  const isCommitted = (status?.latest ?? null) !== null;

  // ------------- hub -------------
  const refreshHub = useCallback(
    async (taskId: string) => {
      const h = await rpc(await getSocket(), "chat.history", { task_id: taskId });
      setMessages((h.messages as never) ?? []);
      setStatus((await rpc(await getSocket(), "task.status", { task_id: taskId })) as never as TaskStatus);
    },
    [getSocket, rpc],
  );

  useEffect(() => {
    if (activeTaskId !== null) {
      void refreshHub(activeTaskId);
    } else {
      setMessages([]);
      setStatus(null);
    }
    setPanel(null);
    setDecomp(null);
  }, [activeTaskId, refreshHub]);

  const sendChat = async (): Promise<void> => {
    if (activeTaskId === null || draft.trim() === "") {
      return;
    }
    setThinking(true);
    try {
      // #660: 对话回路优先 — the agent responds; explicit kind (≠自动) keeps the
      // lightweight routing-only path
      if (kind === "auto") {
        const result = await rpc(await getSocket(), "chat.turn", { task_id: activeTaskId, text: draft.trim() });
        push("rpc", `agent 回应（侦查 ${Array.isArray(result.recon_results) ? (result.recon_results as unknown[]).length : 0} 条）`);
      } else {
        const result = await rpc(await getSocket(), "chat.ingest", { task_id: activeTaskId, text: draft.trim(), kind });
        const receipt = result.receipt as ClassificationBadge;
        push("rpc", `已路由（${CLASSIFIED_BY_LABELS[receipt.classified_by ?? ""] ?? "手动"}）→ ${receipt.routed}`);
      }
      setDraft("");
      await refreshHub(activeTaskId);
    } catch (error) {
      push("error", String(error));
    } finally {
      setThinking(false);
    }
  };

  // ------------- project actions -------------
  const createProject = async (): Promise<void> => {
    if (newName.trim() === "") {
      return;
    }
    try {
      const project_id = `p-${Date.now().toString(36)}`;
      const ws = await getSocket();
      await rpc(ws, "project.create", { project_id, name: newName.trim() });
      await rpc(ws, "project.registerTask", { project_id, task_id: `${project_id}-main`, role: "main" });
      push("rpc", `新研究已建立（主线 ${project_id}-main）`);
      setNewName("");
      setModal(null);
      await refreshTree();
      setActiveTaskId(`${project_id}-main`);
    } catch (error) {
      push("error", String(error));
    }
  };

  const manage = async (projectId: string, action: "archive" | "delete"): Promise<void> => {
    try {
      await rpc(await getSocket(), `project.${action}`, { project_id: projectId });
      push("rpc", `project.${action} ok`);
      if (activeProject?.project_id === projectId) {
        setActiveTaskId(null);
      }
      setMenuFor(null);
      await refreshTree();
    } catch (error) {
      push("error", String(error)); // engine red line verbatim
      setMenuFor(null);
    }
  };

  const pConfig = (): ReactNode | null => {
    if (piConfig === null) {
      return <p className="empty">pi 配置读取中…</p>;
    }
    if (!piConfig.readiness.has_provider_key || !piConfig.readiness.has_model) {
      return (
        <p className="empty">
          keyed 会话未就绪（{!piConfig.readiness.has_provider_key ? "缺 provider key" : "pi 未配置模型"}）——到 ⚙ 设置里补齐后才能提取；不提供模拟提取。
        </p>
      );
    }
    return null;
  };

  // ------------- decomp panel (REAL: chat transcript → pi session) -------------
  const [noRefusals, setNoRefusals] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [starting, setStarting] = useState(false);
  const extractFromChat = async (): Promise<void> => {
    if (activeTaskId === null) {
      return;
    }
    setExtracting(true);
    try {
      const result = await rpc(await getSocket(), "decompose.fromChat", {
        task_id: activeTaskId,
        decomposition_id: `dc-${activeTaskId}`,
        refusals_note: noRefusals ? "none" : undefined,
      });
      setDecomp({
        decomposition_id: `dc-${activeTaskId}`,
        elements: result.elements as never,
        checklist: result.checklist as never,
      });
      push("rpc", `pi 会话提取完成（溯源律丢弃 ${String(result.dropped)} 条无源要素）`);
    } catch (error) {
      push("error", String(error));
    } finally {
      setExtracting(false);
    }
  };

  const startResearch = async (): Promise<void> => {
    if (activeTaskId === null || decomp === null) {
      return;
    }
    setStarting(true);
    try {
      const result = await rpc(await getSocket(), "research.start", {
        task_id: activeTaskId,
        decomposition_id: decomp.decomposition_id,
      });
      push("rpc", `研究已启动：phase=${String(result.phase)} 阶段=${String(result.stages)} 派发=${String(result.dispatched)}`);
      setPanel("research");
      await refreshHub(activeTaskId);
    } catch (error) {
      push("error", String(error));
    } finally {
      setStarting(false);
    }
  };

  // ------------- freeze (human verdict gate) -------------
  const [freezeOpen, setFreezeOpen] = useState(false);
  const [verdict, setVerdict] = useState("");
  const [verdictSummary, setVerdictSummary] = useState("");
  const freezeVerdict = async (): Promise<void> => {
    if (activeTaskId === null || verdict === "") {
      return;
    }
    try {
      const result = await rpc(await getSocket(), "research.freeze", {
        task_id: activeTaskId,
        verdict,
        summary: verdictSummary.trim() !== "" ? verdictSummary.trim() : undefined,
      });
      push("rpc", `已冻结 v${String(result.v)} · ${verdict} · ${String(result.commit_hash).slice(0, 12)}`);
      setFreezeOpen(false);
      setVerdict("");
      setVerdictSummary("");
      await refreshHub(activeTaskId);
    } catch (error) {
      push("error", String(error));
    }
  };

  const removeElement = async (elementClass: string, index: number): Promise<void> => {
    if (decomp === null || activeTaskId === null) {
      return;
    }
    try {
      const result = await rpc(await getSocket(), "decompose.removeElement", {
        task_id: activeTaskId,
        decomposition_id: decomp.decomposition_id,
        element_class: elementClass,
        index,
      });
      setDecomp({ ...decomp, elements: result.elements as never, checklist: result.checklist as never });
    } catch (error) {
      push("error", String(error)); // 确认后编辑 = major pivot verbatim
    }
  };

  const confirmDecomp = async (): Promise<void> => {
    if (decomp === null || activeTaskId === null) {
      return;
    }
    try {
      await rpc(await getSocket(), "decompose.confirm", { task_id: activeTaskId, decomposition_id: decomp.decomposition_id });
      push("rpc", "要素集已冻结为研究宪法（v0）");
      setDecomp({ ...decomp, status: "confirmed" });
      await refreshTree();
    } catch (error) {
      push("error", String(error)); // 预注册缺口 verbatim
    }
  };

  // ------------- research panel -------------
  const refreshResearch = useCallback(async (taskId: string) => {
    const view = await (await fetch(`/api/research/${encodeURIComponent(taskId)}`)).json();
    setResearch(view as never);
    const b = (await (await fetch(`/api/research/${encodeURIComponent(taskId)}/beats`)).json()) as { beats: Array<{ seq: number; event_type: string; summary: string }> };
    setBeats(b.beats);
    setBeat(null);
    setAtView(null);
  }, []);

  useEffect(() => {
    if (panel === "research" && activeTaskId !== null) {
      void refreshResearch(activeTaskId);
    }
  }, [panel, activeTaskId, refreshResearch]);

  const scrubTo = async (t: number): Promise<void> => {
    if (activeTaskId === null) {
      return;
    }
    setBeat(t);
    const view = (await (await fetch(`/api/research/${encodeURIComponent(activeTaskId)}/at/${t}`)).json()) as never;
    setAtView(view as { console: string[]; claims: Record<string, Record<string, unknown>> });
  };

  const openDrawer = async (claimId: string): Promise<void> => {
    if (activeTaskId === null) {
      return;
    }
    const res = await fetch(`/api/research/${encodeURIComponent(activeTaskId)}/lineage/0/${encodeURIComponent(claimId)}`);
    const body = (await res.json()) as { steps?: Array<{ layer: string; detail?: string }>; raw_evidence?: string; error?: string };
    setDrawer({ claimId, lineage: body.error !== undefined ? null : (body as never) });
  };

  // ------------- versions panel -------------
  const refreshVersions = useCallback(async (taskId: string) => {
    const res = await fetch(`/api/versions/${encodeURIComponent(taskId)}`);
    if (res.ok) {
      setVtl((await res.json()) as never);
    }
  }, []);

  useEffect(() => {
    if (panel === "versions" && activeTaskId !== null) {
      void refreshVersions(activeTaskId);
    }
  }, [panel, activeTaskId, refreshVersions]);

  const openSnapshot = async (v: number): Promise<void> => {
    if (activeTaskId === null) {
      return;
    }
    const res = await fetch(`/api/versions/${encodeURIComponent(activeTaskId)}/snapshot/${v}`);
    if (res.ok) {
      setSnap((await res.json()) as never);
      setModal("snapshot");
    }
  };

  const versionAction = async (action: "continue" | "fork"): Promise<void> => {
    if (activeTaskId === null) {
      return;
    }
    try {
      if (action === "continue") {
        await rpc(await getSocket(), "version.continue", { task_id: activeTaskId });
        push("rpc", "继续研究：新草稿自最新提交复制（写时复制）");
      } else {
        const newTaskId = `${activeTaskId}-fork-${Date.now().toString(36).slice(-4)}`;
        await rpc(await getSocket(), "version.fork", { task_id: activeTaskId, v: vtl?.versions[0]?.v ?? 0, new_task_id: newTaskId });
        push("rpc", `分叉 → ${newTaskId}（分叉即继承，落 chat）`);
      }
      await Promise.all([refreshVersions(activeTaskId), refreshTree()]);
    } catch (error) {
      push("error", String(error));
    }
  };

  // ------------- settings modal -------------
  const refreshSettings = useCallback(async () => {
    setSettings((await (await fetch("/api/config/pi")).json()) as never);
  }, []);

  useEffect(() => {
    if (modal === "settings") {
      void refreshSettings();
    }
  }, [modal, refreshSettings]);

  const saveSettings = async (what: "key" | "model"): Promise<void> => {
    try {
      if (what === "key") {
        await rpc(await getSocket(), "config.setProviderKey", {
          provider: provider.trim(),
          api_key: apiKey,
          baseUrl: baseUrl.trim() !== "" ? baseUrl.trim() : undefined,
          model_id: modelId.trim() !== "" ? modelId.trim() : undefined,
        });
        push("rpc", `provider ${provider.trim()} 已写入 pi 的 models.json（审计只记名，key 不回显）`);
        setApiKey("");
      } else {
        await rpc(await getSocket(), "config.setDefaultModel", { model: model.trim() });
        push("rpc", `默认模型 → ${model.trim()}（新开的 pi 会话生效）`);
      }
      await refreshSettings();
      void fetch("/api/config/pi")
        .then((r) => r.json())
        .then((c) => setPiConfig(c as never));
    } catch (error) {
      push("error", String(error));
    }
  };

  // ---------------------------------------------------------------- render
  return (
    <div className="app-shell">
      {/* ============ sidebar ============ */}
      <aside className={`sidebar ${sidebarOpen ? "" : "collapsed"}`}>
        <div className="side-top">
          <button className="new-chat" onClick={() => setModal("new")}>
            <span className="plus">＋</span> 新研究
          </button>
        </div>
        <nav className="side-list">
          {tree.filter((p) => p.status === "active").map((project) => (
            <div key={project.project_id} className="side-group">
              <div
                className={`side-project ${project.status === "archived" ? "archived" : ""}`}
                onClick={() => setActiveTaskId(project.lines.find((l) => l.role === "main")?.task_id ?? null)}
              >
                <span className="glyph">{project.status === "archived" ? "📁" : "🗂"}</span>
                <span className="project-name">{project.name}</span>
                <span
                  className="side-menu"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuFor(menuFor === project.project_id ? null : project.project_id);
                  }}
                >
                  ⋯
                </span>
                {menuFor === project.project_id && (
                  <div className="menu" onClick={(e) => e.stopPropagation()}>
                    {project.status === "active" ? (
                      <button onClick={() => void manage(project.project_id, "archive")}>归档项目</button>
                    ) : (
                      <button className="danger" onClick={() => void manage(project.project_id, "delete")}>
                        删除项目（仅归档可删）
                      </button>
                    )}
                  </div>
                )}
              </div>
              {project.lines.map((line) => (
                <div
                  key={line.task_id}
                  className={`side-task ${line.task_id === activeTaskId ? "active" : ""}`}
                  onClick={() => setActiveTaskId(line.task_id)}
                >
                  <span className="glyph">{line.role === "main" ? "◉" : "⑂"}</span>
                  <span className="task-name">{line.latest !== null ? `v${line.latest.v} · ${line.latest.verdict}` : "进行中"}</span>
                  {line.draft !== null && <span className="mini">草稿</span>}
                </div>
              ))}
            </div>
          ))}
          {tree.filter((p) => p.status === "active").length === 0 && (
            <div className="side-empty">还没有研究——点「新研究」开始</div>
          )}
          {tree.some((p) => p.status === "archived") && (
            <div className="archive-folder">
              <div className="archive-head" onClick={() => setArchiveOpen(!archiveOpen)}>
                {archiveOpen ? "▾" : "▸"} 归档（{tree.filter((p) => p.status === "archived").length}）
              </div>
              {archiveOpen &&
                tree
                  .filter((p) => p.status === "archived")
                  .map((project) => (
                    <div key={project.project_id} className="side-group">
                      <div
                        className="side-project archived"
                        onClick={() => setActiveTaskId(project.lines.find((l) => l.role === "main")?.task_id ?? null)}
                      >
                        <span className="glyph">📁</span>
                        <span className="project-name">{project.name}</span>
                        <span
                          className="side-menu"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuFor(menuFor === project.project_id ? null : project.project_id);
                          }}
                        >
                          ⋯
                        </span>
                        {menuFor === project.project_id && (
                          <div className="menu" onClick={(e) => e.stopPropagation()}>
                            <button className="danger" onClick={() => void manage(project.project_id, "delete")}>
                              删除项目（仅归档可删）
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
            </div>
          )}
        </nav>
        <div className="side-bottom">
          <div className="pi-row">
            <span className={`dot ${piConfig?.keyed_session_ready ? "ok" : "off"}`} />
            <span className="hint">
              {piConfig === null
                ? "pi 配置读取中…"
                : piConfig.keyed_session_ready
                  ? `keyed 就绪 · ${piConfig.default_model}`
                  : "未配置 key（规则回退分类）"}
            </span>
          </div>
          <button className="side-settings" onClick={() => setModal("settings")}>
            ⚙ 设置
          </button>
        </div>
      </aside>

      {/* ============ main column ============ */}
      <div className="main">
        <header className="topbar">
          {!sidebarOpen && (
            <button className="icon-btn" onClick={() => setSidebarOpen(true)} title="展开侧栏">
              ☰
            </button>
          )}
          <div className="title-block">
            <div className="title">
              {activeProject !== null ? activeProject.name : "research-tree"}
              {activeTask !== null && activeTask.role === "fork" && (
                <span className="forkchip">⑂ 支线（fork 来源见「版本」面板）</span>
              )}
            </div>
            {status !== null && (
              <div className="phase">
                {status.latest !== null ? (
                  <span>
                    已提交 v{status.latest.v} · {status.latest.verdict}
                  </span>
                ) : (
                  <span>{status.phase === "chat" ? "对话中" : `研究进行中（${status.phase}）`}</span>
                )}
              </div>
            )}
          </div>
          <div className="top-actions">
            <button className="chip-btn" onClick={() => setPanel(panel === "decomp" ? null : "decomp")} disabled={activeTaskId === null}>
              分解
            </button>
            <button className="chip-btn" onClick={() => setPanel(panel === "research" ? null : "research")} disabled={activeTaskId === null}>
              研究
            </button>
            <button className="chip-btn" onClick={() => setPanel(panel === "versions" ? null : "versions")} disabled={activeTaskId === null}>
              版本
            </button>
            {status !== null && status.phase === "research" && (
              <button className="chip-btn" onClick={() => setFreezeOpen(true)}>
                冻结提交…
              </button>
            )}
            {sidebarOpen && (
              <button className="icon-btn" onClick={() => setSidebarOpen(false)} title="收起侧栏">
                ☰
              </button>
            )}
          </div>
        </header>

        {activeTaskId === null ? (
          <div className="welcome">
            <h1>research-tree</h1>
            <p>接住任何清晰度的想法，做一份诚实的、带反证的研究。</p>
            <button className="primary" onClick={() => setModal("new")}>
              ＋ 新研究
            </button>
          </div>
        ) : (
          <div className={`content ${panel !== null ? "with-panel" : ""}`}>
            <section className="chat-col">
              <div className="stream">
                {messages.map((m) =>
                  m.role === "user" ? (
                    <div key={m.seq} className="msg-user">
                      {m.text}
                    </div>
                  ) : m.role === "rt" ? (
                    m.kind === "reply" ? (
                      <div key={m.seq} className="msg-agent">
                        <div className="agent-tag">rt</div>
                        <div className="agent-body">{m.text}</div>
                        {(() => {
                          const qs = m.receipt_json !== null ? (JSON.parse(String(m.receipt_json)) as { questions?: string[] }).questions : undefined;
                          return Array.isArray(qs) && qs.length > 0 ? (
                            <div className="qchips">
                              {qs.map((q, i) => (
                                <button
                                  key={i}
                                  className="qchip"
                                  onClick={() => {
                                    setDraft(q);
                                  }}
                                >
                                  {q}
                                </button>
                              ))}
                            </div>
                          ) : null;
                        })()}
                      </div>
                    ) : m.kind === "question" ? (
                      <div key={m.seq} className="msg-question" onClick={() => setDraft(m.text)}>
                        ❓ {m.text}
                      </div>
                    ) : m.kind === "recon" ? (
                      <details key={m.seq} className="msg-recon">
                        <summary>🔎 {m.text.slice(0, 60)}…</summary>
                        <div>{m.text}</div>
                      </details>
                    ) : (
                      <div key={m.seq} className="msg-rt">
                        <span className="rt-dot">◉</span> {m.text}
                      </div>
                    )
                  ) : (
                    <div key={m.seq} className="msg-system">
                      {m.text}
                    </div>
                  ),
                )}
                {messages.length === 0 && (
                  <div className="chat-welcome">
                    <h2>{activeProject?.name ?? "新研究"}</h2>
                    <p>把想法倒进来——研究从对话发起、收敛后自动回到对话。</p>
                  </div>
                )}
              </div>
              {/* 追加信息门：胶囊贯穿所有阶段 */}
              <div className="composer-wrap">
                <div className="composer">
                  <select value={kind} onChange={(e) => setKind(e.target.value as UtteranceKind)} className="kind-select">
                    {(Object.keys(KIND_LABELS) as UtteranceKind[]).map((k) => (
                      <option key={k} value={k}>
                        {KIND_LABELS[k]}
                      </option>
                    ))}
                  </select>
                  <textarea
                    rows={1}
                    placeholder="追问、纠正、追加信息……（Enter 发送）"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey && draft.trim() !== "") {
                        e.preventDefault();
                        void sendChat();
                      }
                    }}
                  />
                  <button className="send" onClick={() => void sendChat()} disabled={draft.trim() === "" || thinking}>
                    {thinking ? "…" : "↑"}
                  </button>
                </div>
                <div className="composer-hint">
                  分类：{KIND_LABELS[kind]}（自动 = keyed 时 pi 会话判定，否则规则回退，回执如实标注）
                  {isCommitted && <span> · 已提交，输入框继续可用（继续研究=版本+1，见「版本」面板）</span>}
                </div>
              </div>
            </section>

            {/* ============ canvas panel ============ */}
            {panel !== null && (
              <aside className="canvas">
                <div className="canvas-head">
                  <strong>{panel === "decomp" ? "分解" : panel === "research" ? "研究图谱" : "版本"}</strong>
                  <span className="spacer" />
                  {panel === "versions" && (
                    <>
                      <button className="mini-btn" onClick={() => void versionAction("continue")}>
                        继续研究 +1
                      </button>
                      <button className="mini-btn" onClick={() => void versionAction("fork")}>
                        从此分叉
                      </button>
                    </>
                  )}
                  {panel === "decomp" && decomp === null && (
                    <>
                      <label className="mini-label">
                        <input type="checkbox" checked={noRefusals} onChange={(e) => setNoRefusals(e.target.checked)} />
                        无拒绝点
                      </label>
                      <button className="mini-btn" onClick={() => void extractFromChat()} disabled={extracting || !piConfig?.keyed_session_ready}>
                        {extracting ? "提取中…" : "从对话提取（pi 会话）"}
                      </button>
                    </>
                  )}
                  {panel === "decomp" && decomp !== null && decomp.status === "confirmed" && (
                    <button className="mini-btn" onClick={() => void startResearch()} disabled={starting}>
                      {starting ? "启动中…" : "启动研究"}
                    </button>
                  )}
                  <button className="mini-btn" onClick={() => setPanel(null)}>
                    ✕
                  </button>
                </div>
                <div className="canvas-body">
                  {panel === "decomp" &&
                    (decomp === null ? (
                      pConfig() ?? (
                        <p className="empty">
                          在 hub 里把想法说清楚，然后点上方「从对话提取」——pi 会话从对话转写提取六要素，quote 逐字回查原句（溯源律）。
                        </p>
                      )
                    ) : (
                      <>
                        <div className={`checklist ${decomp.checklist.complete ? "ok" : "gaps"}`}>
                          {decomp.checklist.complete
                            ? "充分性 checklist：六类各 ≥1 ✓"
                            : `充分性缺口：${decomp.checklist.gaps.join("、")}——缺口阻止确认`}
                          {decomp.status === "confirmed" && <span> · 已冻结（变更=重大转向重签）</span>}
                        </div>
                        {ELEMENT_META.map(([cls, label]) => (
                          <div key={cls} className="dgroup">
                            <h4>{label}</h4>
                            {(decomp.elements[cls] ?? []).map((el, i) => (
                              <div key={i} className="element">
                                <div>{String(el.text)}</div>
                                <div className="prov">
                                  来自{String((el.source as Record<string, unknown>).kind) === "attachment" ? "附件" : "你的话"}：“
                                  {String((el.source as Record<string, unknown>).quote)}”
                                </div>
                                {decomp.status !== "confirmed" && (
                                  <button className="mini-btn danger" onClick={() => void removeElement(cls, i)}>
                                    删除
                                  </button>
                                )}
                              </div>
                            ))}
                            {(decomp.elements[cls] ?? []).length === 0 && <div className="empty">待对齐</div>}
                          </div>
                        ))}
                        <button
                          className="primary"
                          onClick={() => void confirmDecomp()}
                          disabled={!decomp.checklist.complete || decomp.status === "confirmed"}
                        >
                          确认无误（要素集冻结为研究宪法）
                        </button>
                        {decomp.status === "confirmed" && (
                          <p className="hint">已确认——点顶部「启动研究」把 claims_preview 变成调研 DAG。</p>
                        )}
                      </>
                    ))}
                  {panel === "research" &&
                    (research === null ? (
                      <p className="empty">加载中…</p>
                    ) : (
                      <>
                        <div className="gnode question">❓ {String(research.question?.title ?? activeTaskId)}</div>
                        <div className="gnode">
                          🧵 {activeTaskId} · {research.transitions.length} 次迁移 · providers: {research.providers.join(", ") || "—"}
                        </div>
                        {research.stages.map((stage) => (
                          <div key={stage.stage_id} className="stage">
                            <div className="stage-head">
                              ▣ {stage.title} <span className="badge">{stage.status}</span>
                              {stage.depends_on.length > 0 && <span className="dep">依赖: {stage.depends_on.join(", ")}</span>}
                            </div>
                            {stage.claim_ids.map((cid) => {
                              const c = (atView?.claims ?? research.claims)[cid];
                              return c === undefined ? null : (
                                <div key={cid} className="claim-row" onClick={() => void openDrawer(cid)}>
                                  {String(c.text)} · 后验 {Number(c.posterior).toFixed(2)} · {String(c.verify_tier)} ·{" "}
                                  {Number(c.posterior) >= 0.9 ? "已决" : "未决"}
                                </div>
                              );
                            })}
                          </div>
                        ))}
                        {Object.entries(atView?.claims ?? research.claims)
                          .filter(([cid]) => !research.stages.some((s) => s.claim_ids.includes(cid)))
                          .map(([cid, c]) => (
                            <div key={cid} className="claim-row" onClick={() => void openDrawer(cid)}>
                              {String(c.text)} · 后验 {Number(c.posterior).toFixed(2)} · {String(c.verify_tier)}
                            </div>
                          ))}
                        <div className="scrubber">
                          <input
                            type="range"
                            min={0}
                            max={Math.max(beats.length, 1)}
                            value={beat ?? beats.length}
                            onChange={(e) => void scrubTo(Number(e.target.value))}
                          />
                          <span className="hint">{beat === null ? `实时（${beats.length} 拍）` : `第 ${beat} 拍`}</span>
                        </div>
                        <div className="console-lines">
                          {(atView?.console ?? beats.map((b) => b.summary)).map((line, i) => (
                            <div key={i} className="cline">
                              {beat !== null ? line : `#${beats[i]?.seq} ${line}`}
                            </div>
                          ))}
                        </div>
                        {drawer !== null && (
                          <div className="drawer">
                            <strong>主张抽屉：{drawer.claimId}</strong>
                            <button className="mini-btn" onClick={() => setDrawer(null)}>
                              ✕
                            </button>
                            {drawer.lineage === null ? (
                              <div className="empty">无 lineage（不伪造溯源路径）</div>
                            ) : (
                              drawer.lineage.steps.map((s, i) => (
                                <div key={i} className="cline">
                                  {i + 1}. {s.layer} {s.detail ?? ""}
                                </div>
                              ))
                            )}
                            <p className="hint">任一结论 ≤3 次点击到达原始证据（#566）</p>
                          </div>
                        )}
                      </>
                    ))}
                  {panel === "versions" &&
                    (vtl === null ? (
                      <p className="empty">加载中…</p>
                    ) : (
                      <>
                        <div className="hint">
                          {vtl.is_main_branch ? "主分支" : `⑂ 支线（fork 自 ${vtl.fork_parent?.task_id}@v${vtl.fork_parent?.v}）`}
                        </div>
                        {vtl.draft !== null && (
                          <div className="draft-row">✎ 草稿（未冻结·不可跟踪）base_v={String(vtl.draft.base_v)}</div>
                        )}
                        {vtl.versions.map((v) => (
                          <div key={v.v} className="vtl-row" onClick={() => void openSnapshot(v.v)}>
                            v{v.v} · {v.verdict} · <code>{v.commit_hash.slice(0, 12)}</code> · {v.summary}
                            {v.forked && <span className="forkchip">⑂ 已分叉</span>}
                          </div>
                        ))}
                        {vtl.versions.length === 0 && <div className="empty">尚无已提交版本</div>}
                      </>
                    ))}
                </div>
              </aside>
            )}
          </div>
        )}
      </div>

      {/* ============ modals ============ */}
      {freezeOpen && (
        <div className="overlay" onClick={() => setFreezeOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>冻结提交 — 三元裁决（人工签署）</h3>
            <p className="hint">裁决永远由你签——问句不是判决。提交后版本不可修改，继续研究=版本+1。</p>
            <div className="verdicts">
              {["GO", "NO-GO", "PARK", "REFRAMED"].map((v) => (
                <button key={v} className={`verdict ${verdict === v ? "picked" : ""}`} onClick={() => setVerdict(v)}>
                  {v}
                </button>
              ))}
            </div>
            <input
              placeholder="研究摘要（可选）"
              value={verdictSummary}
              onChange={(e) => setVerdictSummary(e.target.value)}
            />
            <div className="modal-actions">
              <button className="mini-btn" onClick={() => setFreezeOpen(false)}>
                取消
              </button>
              <button className="primary" onClick={() => void freezeVerdict()} disabled={verdict === ""}>
                签署并提交
              </button>
            </div>
          </div>
        </div>
      )}
      {modal === "new" && (
        <div className="overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>新研究</h3>
            <p className="hint">一个项目 = 一个研究主题</p>
            <input
              autoFocus
              placeholder="研究主题名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && newName.trim() !== "" && void createProject()}
            />
            <div className="modal-actions">
              <button className="mini-btn" onClick={() => setModal(null)}>
                取消
              </button>
              <button className="primary" onClick={() => void createProject()} disabled={newName.trim() === ""}>
                建立研究
              </button>
            </div>
          </div>
        </div>
      )}
      {modal === "settings" && (
        <div className="overlay" onClick={() => setModal(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <h3>设置 — 模型 / API（与 pi agent 同源）</h3>
            {settings === null ? (
              <p className="empty">读取中…</p>
            ) : (
              <>
                <p className="hint">
                  唯一事实源 <code>{settings.config_path}</code>
                  {settings.follows_pi_default
                    ? " · 当前跟随 pi agent 默认配置（rt 未覆盖）"
                    : ` · 默认模型覆盖：${settings.default_model}`}
                  {" "}· provider {settings.providers.join(", ") || "无"} · keyed 会话 {settings.keyed_session_ready ? "就绪" : "未就绪"}。key
                  永不回显，rt 侧无副本。
                </p>
                {settings.models.length > 0 && (
                  <div className="pi-models">
                    {settings.models.map((m) => (
                      <div key={m.id} className="cline">
                        {m.id} · {m.name}
                        {settings.default_model === m.id && <span className="mini"> 当前默认</span>}
                      </div>
                    ))}
                  </div>
                )}
                <div className="row">
                  <select value={model} onChange={(e) => setModel(e.target.value)}>
                    <option value="">— 设默认模型覆盖（可选）—</option>
                    {settings.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.id}
                      </option>
                    ))}
                  </select>
                  <button className="primary" onClick={() => void saveSettings("model")} disabled={model.trim() === ""}>
                    设为默认
                  </button>
                </div>
                <p className="hint">不设置覆盖时，产品跟随 pi agent 自己的默认模型。</p>
                <div className="row">
                  <input placeholder="provider id（如 deepseek）" value={provider} onChange={(e) => setProvider(e.target.value)} />
                  <input placeholder="base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
                </div>
                <div className="row">
                  <input placeholder="模型 id（如 deepseek-flash）" value={modelId} onChange={(e) => setModelId(e.target.value)} />
                  <input
                    type="password"
                    placeholder="API key（保存后不回显）"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                  />
                  <button
                    className="primary"
                    onClick={() => void saveSettings("key")}
                    disabled={provider.trim() === "" || apiKey.trim() === ""}
                  >
                    保存 provider
                  </button>
                </div>
                <p className="hint">写入 pi 自己的 models.json（schema 兼容）；新开的 pi 会话生效。变更落审计事件（只记 provider 名）。</p>
                <div className="ext-block">
                  <h4>默认 pi 扩展</h4>
                  <div className="ext-list">
                    {(settings.default_extensions ?? []).map((e) => (
                      <div key={e.name} className="cline">
                        <span className={`dot ${e.installed ? "ok" : "off"}`} /> {e.name} {e.installed ? "已安装" : "未安装"}
                      </div>
                    ))}
                  </div>
                  <button
                    className="primary"
                    onClick={async () => {
                      try {
                        const result = await rpc(await getSocket(), "config.installExtensions", {});
                        const r = result as { installed: string[]; failed: Array<{ name: string; error: string }> };
                        push("rpc", `扩展安装：${r.installed.length} 个新装，${r.failed.length} 个失败`);
                        await refreshSettings();
                      } catch (error) {
                        push("error", String(error));
                      }
                    }}
                  >
                    安装缺失扩展
                  </button>
                  <p className="hint">billion-context / rpiv-ask-user-question / pi-mcp-adapter / context-mode / pi-web-access —— 默认供应清单（#664）。显式安装，绝不静默。</p>
                </div>
                <div className="modal-actions">
                  <button className="primary" onClick={() => setModal(null)}>
                    完成
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {modal === "snapshot" && snap !== null && (
        <div className="overlay" onClick={() => setModal(null)}>
          <div className="modal wide" onClick={(e) => e.stopPropagation()}>
            <h3>只读快照</h3>
            <div className="frozen-banner">
              🔒 已冻结 v{snap.banner.v} · {snap.banner.verdict} · <code>{snap.banner.commit_hash.slice(0, 12)}</code>
              ——不可再修改；继续研究=版本+1
            </div>
            <pre className="report">{JSON.stringify(snap.report, null, 2)}</pre>
            <div className="modal-actions">
              <button className="primary" onClick={() => setModal(null)}>
                回当前工作区
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
