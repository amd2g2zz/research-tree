/** WebUI P0/P1 (issue #633): home = default landing with the card wall
 * (create / list-with-vitals / archive / delete-archived-only — engine red
 * lines surfaced verbatim) and the P1 sidebar tree (project → research lines
 * main/fork → version nodes with fork markers + the draft row
 * 未冻结·不可跟踪). Data comes from /api/tree assembled over #571/#548. */

import { useCallback, useEffect, useRef, useState } from "react";

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
interface LineNode {
  task_id: string;
  role: "main" | "fork";
  latest: { v: number; verdict: string; commit_hash: string; summary: string } | null;
  versions: VersionNode[];
  draft: { base_v: number | null; updated_at: string } | null;
}
interface TreeNode extends ProjectCard {
  vitals: {
    research_lines: number;
    latest: { v: number; verdict: string; commit_hash: string } | null;
    elapsed_ms: number;
  };
  lines: LineNode[];
}
interface LogLine {
  kind: "engine" | "rpc" | "error";
  text: string;
}
type UtteranceKind = "preference" | "claim" | "guess" | "branch";
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
const KIND_LABELS: Record<UtteranceKind, string> = {
  preference: "偏好/意图",
  claim: "事实主张",
  guess: "方案猜测",
  branch: "分支/岔路",
};

const WALK_STEPS = [
  {
    event: "open-draft",
    snapshot: { elements: {}, claims: [], evidence_refs: [], report: {}, deleted_nodes: [] },
    base_v: null,
  },
  {
    event: "attach",
    decomposition_id: "dc-spike",
    decomposition: {
      requirements: [{ text: "deploy on 2C4G fast", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" } }],
      constraints: [{ text: "2C4G is a guess", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" }, hardness: "guessed" }],
      background: [],
      intents: [{ text: "ship fast", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" } }],
      refusals: [],
      difficulties: [{ text: "2C4G memory ceiling", source: { kind: "chat-message", ref: "msg:1", quote: "2C4G 越快上越好" }, kill_candidates: ["c-mob"] }],
      claims_preview: [{ id: "c-mob", text: "2C4G suffices", kill_condition: "OOM under load" }],
    },
    plan: {
      plan_id: "plan-spike",
      stages: [{ id: "s1", title: "recon", claim_ids: [], depends_on: [] }],
      budget: { capMs: 12 * 3600 * 1000 },
      yaw_checks: [
        { slot: "plan-level", mode: "auto" },
        { slot: "problem-level", mode: "human" },
        { slot: "knowledge-level", mode: "auto" },
      ],
    },
  },
  { event: "confirm" },
  { event: "sign" },
  { event: "research-completed" },
];

export function App() {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [piConfig, setPiConfig] = useState<{ present: boolean; default_model: string | null; auth_providers: string[] } | null>(null);
  const [log, setLog] = useState<LogLine[]>([]);
  const [running, setRunning] = useState(false);
  const [name, setName] = useState("");
  const socketRef = useRef<WebSocket | null>(null);
  // ---------------- P2 hub state ----------------
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<TaskStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<UtteranceKind>("preference");

  const push = useCallback((kind: LogLine["kind"], text: string) => {
    setLog((prev) => [...prev.slice(-199), { kind, text }]);
  }, []);

  const refreshTree = useCallback(async () => {
    const res = await fetch("/api/tree");
    const projects = ((await res.json()) as { projects: TreeNode[] }).projects;
    setTree(projects);
    setSelected((current) => current ?? projects.find((p) => p.status === "active")?.project_id ?? null);
  }, []);

  useEffect(() => {
    void refreshTree();
    void fetch("/api/config/pi")
      .then((r) => r.json())
      .then((c) => setPiConfig(c as never));
  }, [refreshTree]);

  const connect = useCallback((): Promise<WebSocket> => {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => resolve(ws);
      ws.onerror = reject;
    });
  }, []);

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

  const getSocket = useCallback(async (): Promise<WebSocket> => {
    if (socketRef.current === null || socketRef.current.readyState > 1) {
      socketRef.current = await connect();
    }
    return socketRef.current;
  }, [connect]);

  const createProject = async (): Promise<void> => {
    if (name.trim() === "") {
      return;
    }
    try {
      const project_id = `p-${Date.now().toString(36)}`;
      const ws = await getSocket();
      await rpc(ws, "project.create", { project_id, name: name.trim() });
      await rpc(ws, "project.registerTask", { project_id, task_id: `${project_id}-main`, role: "main" });
      push("rpc", `项目已创建，落其首页（主线 ${project_id}-main）`);
      setName("");
      await refreshTree();
      setSelected(project_id);
    } catch (error) {
      push("error", String(error));
    }
  };

  const manage = async (projectId: string, action: "archive" | "delete"): Promise<void> => {
    try {
      await rpc(await getSocket(), `project.${action}`, { project_id: projectId });
      push("rpc", `project.${action} ok`);
      if (selected === projectId) {
        setSelected(null);
      }
      await refreshTree();
    } catch (error) {
      push("error", String(error)); // engine red line surfaced verbatim
    }
  };

  const runWalk = async (): Promise<void> => {
    setRunning(true);
    try {
      const project = tree.find((p) => p.project_id === selected);
      if (project === undefined) {
        throw new Error("先建一个项目");
      }
      push("rpc", "端到端演练开始：分解 → 签署 → 研究 → 冻结提交");
      const result = await rpc(await getSocket(), "research.launch", {
        task_id: project.lines.find((l) => l.role === "main")?.task_id ?? `${project.project_id}-main`,
        pre_signed: { verdict: "GO", summary: "webui 演练提交" },
        steps: WALK_STEPS,
      });
      push("rpc", `演练完成：outcome=${String(result.outcome)} events=${String(result.events)}`);
      await refreshTree();
    } catch (error) {
      push("error", String(error));
    } finally {
      setRunning(false);
    }
  };

  const selectedProject = tree.find((p) => p.project_id === selected) ?? null;

  // ---------------- P3 decomposition page ----------------
  const [decomp, setDecomp] = useState<{
    decomposition_id: string;
    elements: Record<string, Array<Record<string, unknown>>>;
    checklist: { complete: boolean; gaps: string[] };
    status?: string;
  } | null>(null);

  const prepareDecomp = async (): Promise<void> => {
    if (mainTaskId === null) {
      return;
    }
    try {
      // 演练：extraction 由 LLM 侧（pi 会话）产出；keyed session 接入前此处注入 fixture
      const result = await rpc(await getSocket(), "decompose.prepare", {
        task_id: mainTaskId,
        decomposition_id: `dc-${mainTaskId}`,
        extraction: WALK_STEPS.find((s) => s.event === "attach")?.decomposition,
        refusals_note: "none",
      });
      setDecomp({
        decomposition_id: `dc-${mainTaskId}`,
        elements: result.elements as never,
        checklist: result.checklist as never,
      });
      push("rpc", `分解草稿已保存（溯源律丢弃 ${String(result.dropped)} 条无源要素）`);
    } catch (error) {
      push("error", String(error));
    }
  };

  const removeElement = async (elementClass: string, index: number): Promise<void> => {
    if (decomp === null || mainTaskId === null) {
      return;
    }
    try {
      const result = await rpc(await getSocket(), "decompose.removeElement", {
        task_id: mainTaskId,
        decomposition_id: decomp.decomposition_id,
        element_class: elementClass,
        index,
      });
      setDecomp({ ...decomp, elements: result.elements as never, checklist: result.checklist as never });
      push("rpc", `已删除 ${elementClass}[${index}]（编辑权在确认前）`);
    } catch (error) {
      push("error", String(error)); // 确认后编辑 = major pivot，引擎拒绝 verbatim
    }
  };

  const confirmDecomp = async (): Promise<void> => {
    if (decomp === null || mainTaskId === null) {
      return;
    }
    try {
      await rpc(await getSocket(), "decompose.confirm", { task_id: mainTaskId, decomposition_id: decomp.decomposition_id });
      push("rpc", "要素集已冻结为研究宪法（v0）；启动研究");
      setDecomp({ ...decomp, status: "confirmed" });
      await refreshTree();
    } catch (error) {
      push("error", String(error)); // 预注册缺口 verbatim
    }
  };

  const ELEMENT_META: Array<[string, string]> = [
    ["requirements", "🎯 需求"],
    ["constraints", "📌 条件约束"],
    ["background", "📖 任务背景"],
    ["intents", "💡 用户意图"],
    ["refusals", "🚫 拒绝点"],
    ["difficulties", "⚠ 难点→kill 候选"],
  ];

  // ---------------- P2 hub actions ----------------
  const mainTaskId = selectedProject?.lines.find((l) => l.role === "main")?.task_id ?? null;

  const refreshHub = useCallback(
    async (taskId: string) => {
      const h = await rpc(await getSocket(), "chat.history", { task_id: taskId });
      setMessages((h.messages as never) ?? []);
      setStatus((await rpc(await getSocket(), "task.status", { task_id: taskId })) as never as TaskStatus);
    },
    [getSocket, rpc],
  );

  useEffect(() => {
    if (mainTaskId !== null) {
      void refreshHub(mainTaskId);
    } else {
      setMessages([]);
      setStatus(null);
    }
  }, [mainTaskId, refreshHub]);

  const sendChat = async (): Promise<void> => {
    if (mainTaskId === null || draft.trim() === "") {
      return;
    }
    try {
      const result = await rpc(await getSocket(), "chat.ingest", { task_id: mainTaskId, kind, text: draft.trim() });
      const routed = (result as { receipt: { routed: string } }).receipt.routed;
      push("rpc", `已路由：${KIND_LABELS[kind]} → ${routed}`);
      setDraft("");
      await refreshHub(mainTaskId);
    } catch (error) {
      push("error", String(error));
    }
  };

  return (
    <div className="app">
      <header>
        <h1 onClick={() => setSelected(tree.find((p) => p.status === "active")?.project_id ?? null)}>research-tree</h1>
        <div className="pi-config">
          {piConfig === null
            ? "pi 配置读取中…"
            : piConfig.present
              ? `pi 同源配置：默认模型 ${piConfig.default_model ?? "未设置"} · provider ${piConfig.auth_providers.join(", ") || "无"}`
              : "未找到 pi 配置（~/.pi/agent）"}
        </div>
      </header>
      <div className="layout">
        {/* ---------------- P1 侧栏研究树 ---------------- */}
        <nav className="sidebar card">
          <h2>研究树</h2>
          {tree.map((project) => (
            <div key={project.project_id} className="tree-project">
              <div className={`tree-row project ${project.status}`} onClick={() => setSelected(project.project_id)}>
                📁 {project.name}
                <span className={`status ${project.status}`}>{project.status}</span>
              </div>
              {project.lines.map((line) => (
                <div key={line.task_id} className="tree-line">
                  <div className={`tree-row line-node ${line.role}`}>
                    {line.role === "main" ? "●" : "⑂"} {line.task_id}
                  </div>
                  {line.draft !== null && <div className="tree-row draft">✎ 草稿（未冻结·不可跟踪）</div>}
                  {line.versions.map((v) => (
                    <div key={v.v} className="tree-row version">
                      v{v.v} · {v.verdict} · <code>{v.commit_hash.slice(0, 8)}</code>
                      {v.forked && <span className="fork-mark">⑂ 已分叉</span>}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ))}
        </nav>
        <main>
          {/* ---------------- P0 项目首页 ---------------- */}
          <section className="card">
            <h2>项目首页（应用默认落点）</h2>
            <div className="row">
              <input
                placeholder="新项目名称（一个项目 = 一个研究主题）"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && name.trim() !== "" && void createProject()}
              />
              <button onClick={() => void createProject()} disabled={name.trim() === ""}>
                建项目
              </button>
            </div>
            {selectedProject === null ? (
              <p className="empty">从研究树选择项目</p>
            ) : (
              <>
                <div className="card-head">
                  <strong>{selectedProject.name}</strong>
                  {selectedProject.attachments.map((a) => (
                    <span key={a.id} className="chip">
                      {a.label}
                    </span>
                  ))}
                  <span className="spacer" />
                  {selectedProject.status === "active" ? (
                    <button className="ghost" onClick={() => void manage(selectedProject.project_id, "archive")}>
                      归档
                    </button>
                  ) : (
                    <button className="ghost danger" onClick={() => void manage(selectedProject.project_id, "delete")}>
                      删除（仅归档可删）
                    </button>
                  )}
                </div>
                <div className="vitals">
                  <div>研究线：{selectedProject.vitals.research_lines}</div>
                  <div>
                    主分支最新：{" "}
                    {selectedProject.vitals.latest === null ? (
                      "未提交"
                    ) : (
                      <code>
                        v{selectedProject.vitals.latest.v} · {selectedProject.vitals.latest.verdict} ·{" "}
                        {selectedProject.vitals.latest.commit_hash.slice(0, 12)}
                      </code>
                    )}
                  </div>
                  <div>已用时间：{Math.round(selectedProject.vitals.elapsed_ms / 1000)}s</div>
                </div>
                {selectedProject.vitals.latest !== null && <button className="ghost">查看最新报告（快照视图 #637 落地）</button>}
                <button onClick={() => void runWalk()} disabled={running || selectedProject.status !== "active"}>
                  {running ? "研究推进中…" : "端到端演练（分解→签署→研究→冻结提交）"}
                </button>
                <p className="hint">演练走 #579 headless 全链路；真实对话/分解页在 #634/#635 落地。</p>
              </>
            )}
          </section>
          {/* ---------------- P2 hub 对话页（项目主界面） ---------------- */}
          <section className="card chat">
            <h2>对话（hub）{mainTaskId !== null && <code className="task-id">{mainTaskId}</code>}</h2>
            {/* 任务状态卡：运行中→查看研究；收敛→报告+冻结；提交后消失（phase 回 chat 且有 latest） */}
            {status !== null && status.latest === null && status.phase !== "chat" && (
              <div className="status-card">研究进行中（phase: {status.phase}）→ 查看研究</div>
            )}
            {status !== null && status.latest !== null && (
              <div className="status-card aligned">
                已提交 v{status.latest.v} · {status.latest.verdict} · <code>{status.latest.commit_hash.slice(0, 12)}</code>
                <span className="hint">（状态卡提交后消失；继续研究=版本+1）</span>
              </div>
            )}
            <div className="messages">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.seq} className="msg user">
                    {m.text}
                  </div>
                ) : (
                  <div key={m.seq} className="msg rt">
                    {m.text}
                  </div>
                ),
              )}
              {messages.length === 0 && <div className="empty">研究从对话发起——把想法倒进来</div>}
            </div>
            {/* 追加信息门：输入框贯穿所有阶段 */}
            <div className="row chat-input">
              <select value={kind} onChange={(e) => setKind(e.target.value as UtteranceKind)}>
                {(Object.keys(KIND_LABELS) as UtteranceKind[]).map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABELS[k]}
                  </option>
                ))}
              </select>
              <input
                placeholder="追加信息（贯穿所有阶段）"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && draft.trim() !== "" && void sendChat()}
                disabled={mainTaskId === null}
              />
              <button onClick={() => void sendChat()} disabled={mainTaskId === null || draft.trim() === ""}>
                发送
              </button>
            </div>
            <p className="hint">
              语义分类当前显式选择——LLM 分类器随 keyed-session provisioning（#588）接入后自动判定。
              <button className="ghost inline" disabled={(status?.routed_count ?? 0) < 3}>
                聊得差不多了 → 分解（≥3 句被路由后可用；P3 页面 #635 落地）
              </button>
            </p>
          </section>
          {/* ---------------- P3 分解页 ---------------- */}
          <section className="card decomp">
            <h2>分解（六要素 · 溯源律可见 · 编辑权在确认前）</h2>
            {decomp === null ? (
              <button onClick={() => void prepareDecomp()} disabled={mainTaskId === null}>
                生成分解草稿（extraction 由 LLM 侧产出；演练注入 fixture）
              </button>
            ) : (
              <>
                <div className={`checklist ${decomp.checklist.complete ? "ok" : "gaps"}`}>
                  {decomp.checklist.complete
                    ? "充分性 checklist：六类各 ≥1 ✓（拒绝点已显式为无）"
                    : `充分性缺口：${decomp.checklist.gaps.join("、")} —— 缺口阻止确认`}
                  {decomp.status === "confirmed" && <span> · 已冻结（确认后变更=重大转向重签）</span>}
                </div>
                <div className="wall">
                  {ELEMENT_META.map(([cls, label]) => (
                    <div key={cls} className="cell">
                      <h3>{label}</h3>
                      {(decomp.elements[cls] ?? []).map((el, i) => (
                        <div key={i} className="element">
                          <div>{String(el.text)}</div>
                          <div className="prov">
                            来自{String((el.source as Record<string, unknown>).kind) === "attachment" ? "附件" : "你的话"}：
                            “{String((el.source as Record<string, unknown>).quote)}”
                          </div>
                          {decomp.status !== "confirmed" && (
                            <button className="ghost tiny" onClick={() => void removeElement(cls, i)}>
                              删除
                            </button>
                          )}
                        </div>
                      ))}
                      {(decomp.elements[cls] ?? []).length === 0 && <div className="empty">待对齐</div>}
                    </div>
                  ))}
                </div>
                <button onClick={() => void confirmDecomp()} disabled={!decomp.checklist.complete || decomp.status === "confirmed"}>
                  确认无误，启动研究 v0（缺口阻止确认）
                </button>
              </>
            )}
          </section>
          <section className="card console">
            <h2>引擎事件流</h2>
            <div className="log">
              {log.map((line, i) => (
                <div key={i} className={`line ${line.kind}`}>
                  {line.text}
                </div>
              ))}
              {log.length === 0 && <div className="empty">等待事件…</div>}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
