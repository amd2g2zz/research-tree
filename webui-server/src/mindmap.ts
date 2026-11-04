/** Mindmap tree (issue #683, WebUI v3 确认阶段 full-canvas page).

The chat produces a messy transcript; the mindmap turns it into a
STRUCTURED tree the user confirms before research:

- root = the core question distilled from the conversation
- depth-1 branches: at least 限制条件 / 任务背景 / 调研目标 (more allowed)
- each branch decomposes up to 5 levels
- every node carries a provenance quote mapped back to the transcript
  (溯源律 — unmapped quotes keep no provenance and are flagged)

Storage: migration v9 `mindmaps` (task_id PK, tree_json, status
draft|confirmed). Editing is draft-only; confirming freezes the tree and
mechanically derives the research stages (each LEAF node becomes a stage).
*/

export interface MindNode {
  id: string;
  text: string;
  /** branch identity for depth-1 nodes — survives editor renaming */
  branch?: string;
  /** provenance quote mapped back to the transcript (溯源律) */
  quote?: string;
  children: MindNode[];
}

export interface MindTree {
  root: MindNode;
}

export const MAX_DEPTH = 5;
export const REQUIRED_BRANCHES = ["限制条件", "任务背景", "调研目标"] as const;

export function mindmapPrompt(messages: Array<{ seq: number; role: string; text: string }>): string {
  const transcript = messages
    .filter((m) => m.role === "user" || m.role === "rt")
    .map((m) => `[${m.seq}][${m.role}] ${m.text}`)
    .join("\n");
  return (
    "你是研究结构师。把下面的对话整理成思维导图 JSON（只输出 JSON）：\n" +
    '{"root":{"text":"核心问题一句话","children":' +
    '[{"text":"限制条件","children":[{"text":"...","quote":"原话片段"}]},' +
    '{"text":"任务背景","children":[...]},{"text":"调研目标","children":[...]},' +
    '{"text":"…更多二级主题","children":[...]}]}}\n' +
    "规则：\n" +
    "1. root = 从对话提炼的核心问题（一句话）。\n" +
    "2. 二级主题至少包含：限制条件、任务背景、调研目标（可以更多）。\n" +
    "3. 每个二级主题向下分解，总深度 ≤5 层；quote 必须逐字来自对话原句（溯源律）。\n" +
    "4. 叶子节点 = 未来调研要验证的具体命题。\n\n对话：\n" +
    transcript
  );
}

export interface ParsedMindmap {
  tree: MindTree;
  dropped: number;
  depth: number;
}

/** Parse the model's tree JSON, map quotes back to the transcript, enforce ≤5 depth. */
export function parseMindmap(stdout: string, messages: Array<{ seq: number; role: string; text: string }>): ParsedMindmap {
  const match = /\{[\s\S]*\}/.exec(stdout);
  if (match === null) {
    throw new Error("mindmap returned no JSON object");
  }
  let raw: { root?: { text?: string; children?: unknown[] } };
  try {
    raw = JSON.parse(match[0]) as { root?: { text?: string; children?: unknown[] } };
  } catch {
    throw new Error(`mindmap returned malformed JSON: ${match[0].slice(0, 60)}`);
  }
  if (raw.root === undefined || typeof raw.root.text !== "string" || raw.root.text === "") {
    throw new Error("mindmap returned no root");
  }
  let dropped = 0;

  const convert = (nodes: unknown[], depth: number): MindNode[] =>
    nodes
      .filter((n): n is Record<string, unknown> => typeof n === "object" && n !== null && typeof (n as Record<string, unknown>).text === "string")
      .map((n) => {
        const quote = typeof n.quote === "string" ? n.quote : undefined;
        let provenance: string | undefined;
        if (quote !== undefined && quote !== "") {
          const hit = messages.find((m) => m.role === "user" && m.text.includes(quote));
          provenance = hit !== undefined ? quote : undefined;
          if (provenance === undefined) {
            dropped += 1;
          }
        }
        const kids = Array.isArray(n.children) ? convert(n.children, depth + 1) : [];
        return {
          id: `n${depth}-${Math.abs(hash(n.text as string + depth))}`,
          text: n.text as string,
          quote: provenance,
          children: depth >= MAX_DEPTH ? [] : kids,
        };
      });

  const rootChildren = convert(Array.isArray(raw.root.children) ? raw.root.children : [], 1);
  // tag depth-1 nodes with branch identity (survives renaming in the editor)
  const branchNames = ["限制条件", "任务背景", "调研目标", "拒绝点", "难点"];
  for (const [i, child] of rootChildren.entries()) {
    const match = branchNames.find((bn) => child.text.includes(bn) || bn.includes(child.text));
    if (match !== undefined) {
      child.branch = match;
    }
  }
  const depth = treeDepth(rootChildren);
  return { tree: { root: { id: "root", text: raw.root.text, children: rootChildren } }, dropped, depth };
}

function treeDepth(nodes: MindNode[]): number {
  if (nodes.length === 0) {
    return 1;
  }
  return 1 + Math.max(...nodes.map((c) => treeDepth(c.children)));
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return h;
}

/** Mechanical plan from the confirmed tree: every LEAF node = one stage
 * (调研要验证的命题), no LLM. Depth in the DAG = tree depth of the leaf. */
export function mechanicalPlan(tree: MindTree): Array<{ id: string; title: string; claim_ids: string[]; depends_on: string[] }> {
  const stages: Array<{ id: string; title: string; claim_ids: string[]; depends_on: string[] }> = [];
  const walk = (node: MindNode, prefix: string): void => {
    for (const child of node.children) {
      if (child.children.length === 0) {
        const id = `stage-${prefix}-${child.id}`;
        stages.push({ id, title: `verify: ${child.text}`, claim_ids: [child.id], depends_on: [] });
      } else {
        walk(child, `${prefix}-${child.id}`);
      }
    }
  };
  walk(tree.root, "root");
  return stages;
}

/** In-place tree edit operations (draft only — caller enforces). */
export function editNode(
  tree: MindTree,
  op: { action: "rename" | "addChild" | "delete"; nodeId: string; text?: string },
): boolean {
  const visit = (node: MindNode): { parent: MindNode | null; node: MindNode } | null => {
    for (const child of node.children) {
      if (child.id === op.nodeId) {
        return { parent: node, node: child };
      }
      const hit = visit(child);
      if (hit !== null) {
        return hit;
      }
    }
    return null;
  };
  if (op.nodeId === tree.root.id) {
    if (op.action === "rename" && op.text !== undefined) {
      tree.root.text = op.text;
      return true;
    }
    return false; // root cannot be deleted
  }
  const hit = visit(tree.root);
  if (hit === null) {
    return false;
  }
  if (op.action === "rename" && op.text !== undefined) {
    hit.node.text = op.text;
    return true; // branch identity is preserved (rename changes display text only)
  }
  if (op.action === "addChild") {
    hit.node.children.push({ id: `n-${Date.now().toString(36)}-${Math.abs(hash(hit.node.id + (op.text ?? "")))}`, text: op.text ?? "", children: [] });
    return true;
  }
  if (op.action === "delete") {
    hit.parent!.children = hit.parent!.children.filter((c) => c.id !== op.nodeId);
    return true;
  }
  return false;
}
