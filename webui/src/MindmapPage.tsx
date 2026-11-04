/** MindmapPage (issue #683): full-canvas editable mindmap.

Chat messiness → structured tree: root = core question, depth-1 branches
(限制条件/任务背景/调研目标/…), ≤5 levels, provenance quotes. Editable
inline (rename/add/delete). Confirm → mechanical stages → research canvas.
*/

import { useCallback, useEffect, useState, type ReactNode } from "react";

interface MindNodeData {
  id: string;
  text: string;
  quote?: string;
  children: MindNodeData[];
}

interface Props {
  taskId: string;
  onBack: () => void;
  onConfirmed: () => void;
  rpcFn: (method: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>;
  pushLog: (kind: "rpc" | "error", text: string) => void;
}

export function MindmapPage({ taskId, onBack, onConfirmed, rpcFn, pushLog }: Props) {
  const [tree, setTree] = useState<MindTreeData | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await rpcFn("mindmap.get", { task_id: taskId });
      const t = r.tree as MindTreeData | null;
      if (t !== null) {
        setTree(t);
        setConfirmed(r.status === "confirmed");
      }
    } catch {
      // no mindmap yet
    }
  }, [taskId, rpcFn]);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await rpcFn("mindmap.generate", { task_id: taskId });
      setTree(r.tree as MindTreeData);
      setConfirmed(false);
      pushLog("rpc", `思维导图已生成（丢弃 ${String(r.dropped)} 条，深度 ${String(r.depth)}）`);
    } catch (e) {
      setError(String(e));
      pushLog("error", String(e));
    } finally {
      setLoading(false);
    }
  };

  const edit = async (action: string, nodeId: string, text?: string) => {
    try {
      const r = await rpcFn("mindmap.editNode", { task_id: taskId, action, node_id: nodeId, text });
      setTree(r.tree as MindTreeData);
    } catch (e) {
      pushLog("error", String(e));
    }
  };

  const confirm = async () => {
    if (!tree) return;
    try {
      await rpcFn("mindmap.confirm", { task_id: taskId });
      pushLog("rpc", "思维导图已确认——调研阶段启动");
      setConfirmed(true);
      onConfirmed();
    } catch (e) {
      pushLog("error", String(e));
    }
  };

  const renderNode = (node: MindNodeData, depth: number): ReactNode => (
    <div key={node.id} className="mm-branch">
      <div className={`mm-node ${depth === 0 ? "root" : depth === 1 ? "branch" : "leaf"}`}>
        {editingId === node.id ? (
          <input
            className="mm-edit"
            value={editText}
            autoFocus
            onChange={(e) => setEditText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && edit("rename", node.id, editText)}
            onBlur={() => setEditingId(null)}
          />
        ) : (
          <span className="mm-text" onDoubleClick={() => { setEditingId(node.id); setEditText(node.text); }}>
            {node.text}
          </span>
        )}
        {node.quote && <div className="mm-quote">“{node.quote}”</div>}
        {!confirmed && depth > 0 && (
          <div className="mm-actions">
            <button className="mm-btn" onClick={() => { setEditingId(node.id); setEditText(node.text); }}>✎</button>
            <button className="mm-btn" onClick={() => edit("addChild", node.id, "新节点")}>＋</button>
            <button className="mm-btn" onClick={() => edit("delete", node.id)}>✕</button>
          </div>
        )}
      </div>
      {node.children.length > 0 && <div className="mm-children">{node.children.map((c) => renderNode(c, depth + 1))}</div>}
    </div>
  );

  return (
    <div className="mm-page">
      <div className="mm-toolbar">
        <button className="mini-btn" onClick={onBack}>← 回到对话</button>
        <span className="mm-task">{taskId}</span>
        <span style={{ flex: 1 }} />
        {!tree && (
          <button className="primary" onClick={generate} disabled={loading}>
            {loading ? "生成中…" : "从对话生成思维导图"}
          </button>
        )}
        {tree && !confirmed && (
          <button className="primary" onClick={confirm}>确认，开始调研</button>
        )}
        {confirmed && <span style={{ color: "#1d7a1d", fontWeight: 600 }}>已确认</span>}
      </div>
      <div className="mm-canvas">
        {!tree ? (
          <div className="mm-placeholder">
            <p>点击上方按钮从对话生成思维导图。pi 会话提炼核心问题与分支，quote 逐字回查。</p>
            {error && <p style={{ color: "#c0392b" }}>{error}</p>}
          </div>
        ) : (
          renderNode(tree.root, 0)
        )}
      </div>
    </div>
  );
}

interface MindTreeData {
  root: MindNodeData;
}
