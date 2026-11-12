/** 确认阶段：XMind 式真脑图画布（用户裁定 2026-11-06；RPC 来自 #683）。
 * React Flow 渲染横向 tidy-tree 脑图 + 底部 minimap（视口自动跟随）+
 * 分支折叠（+N）；大纲收进抽屉默认折叠，点节点画布居中联动；
 * quote 溯源、确认前可编辑（rename/addChild/delete）。 */

import "@xyflow/react/dist/style.css";
import {
	ArrowLeftOutlined,
	DeleteOutlined,
	EditOutlined,
	PlusOutlined,
	UnorderedListOutlined,
} from "@ant-design/icons";
import {
	Background,
	BackgroundVariant,
	Controls,
	type Edge,
	Handle,
	MiniMap,
	type Node,
	type NodeProps,
	Position,
	ReactFlow,
	ReactFlowProvider,
	useReactFlow,
} from "@xyflow/react";
import {
	App,
	Button,
	Drawer,
	Empty,
	Input,
	Modal,
	Popconfirm,
	Space,
	Spin,
	Tag,
	Tooltip,
	Tree,
	Typography,
} from "antd";
import type { DataNode } from "antd/es/tree";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { rpc } from "../lib/rpc";
import { attachWheelPanZoom } from "../lib/rfWheel";
import type { MindNode } from "../lib/types";

interface Props {
	taskId: string;
	onBack: () => void;
	onConfirmed: () => void;
	/** chat hub 卡片点进来 = 用户确认抽取，挂载即生成 */
	autoGenerate?: boolean;
}

interface MindmapState {
	tree: { root: MindNode };
	status: string | null;
}

// ── 平衡模式布局（XMind 平衡导图）：根居中，分支按体量分左右 ──
const NODE_W = 232;
const NODE_H = 64;
const GAP_X = 76;
const GAP_Y = 16;

type Side = "right" | "left";

interface LaidNode {
	node: MindNode;
	depth: number;
	side: Side | "root";
	x: number; // 卡片左上角，根中心为原点
	y: number;
	children: LaidNode[];
	collapsedHere: boolean;
}

const leafCount = (n: MindNode): number =>
	n.children.length === 0 ? 1 : n.children.reduce((s, c) => s + leafCount(c), 0);

/** 一侧分支的纵向 tidy 排布：共享叶子游标；dir=+1 右侧向外长，dir=-1 左侧镜像。 */
function layoutSide(
	branches: MindNode[],
	collapsed: Set<string>,
	side: Side,
): { roots: LaidNode[]; height: number; count: number } {
	const dir = side === "right" ? 1 : -1;
	const baseX = dir * (NODE_W / 2 + GAP_X);
	let cursorY = 0;
	let count = 0;
	const walk = (node: MindNode, depth: number): LaidNode => {
		count += 1;
		const isCollapsed = collapsed.has(node.id) && node.children.length > 0;
		const kids = isCollapsed
			? []
			: node.children.map((c) => walk(c, depth + 1));
		const x =
			dir === 1
				? baseX + (depth - 1) * (NODE_W + GAP_X)
				: baseX - NODE_W - (depth - 1) * (NODE_W + GAP_X);
		if (kids.length === 0) {
			const y = cursorY;
			cursorY += NODE_H + GAP_Y;
			return {
				node,
				depth,
				side,
				x,
				y,
				children: [],
				collapsedHere: isCollapsed,
			};
		}
		const first = kids[0]?.y ?? 0;
		const last = kids[kids.length - 1]?.y ?? 0;
		const y = (first + last) / 2;
		return {
			node,
			depth,
			side,
			x,
			y,
			children: kids,
			collapsedHere: isCollapsed,
		};
	};
	const roots = branches.map((b) => walk(b, 1));
	return { roots, height: Math.max(cursorY - GAP_Y, NODE_H), count };
}

const shiftSide = (nodes: LaidNode[], dy: number): void => {
	for (const n of nodes) {
		n.y += dy;
		shiftSide(n.children, dy);
	}
};

/** 平衡模式：根居中 (0,0)，一级分支按子树叶子数贪心分左右，两侧各自垂直居中。 */
function layoutBalanced(
	root: MindNode,
	collapsed: Set<string>,
): { root: LaidNode; count: number } {
	const isCollapsedRoot = collapsed.has(root.id) && root.children.length > 0;
	const kids = isCollapsedRoot ? [] : root.children;
	const right: MindNode[] = [];
	const left: MindNode[] = [];
	let rLeaves = 0;
	let lLeaves = 0;
	for (const k of kids) {
		if (rLeaves <= lLeaves) {
			right.push(k);
			rLeaves += leafCount(k);
		} else {
			left.push(k);
			lLeaves += leafCount(k);
		}
	}
	const r = layoutSide(right, collapsed, "right");
	const l = layoutSide(left, collapsed, "left");
	shiftSide(r.roots, -r.height / 2);
	shiftSide(l.roots, -l.height / 2);
	const rootNode: LaidNode = {
		node: root,
		depth: 0,
		side: "root",
		x: -NODE_W / 2,
		y: -NODE_H / 2,
		children: [...r.roots, ...l.roots],
		collapsedHere: isCollapsedRoot,
	};
	return { root: rootNode, count: 1 + r.count + l.count };
}

const flatten = (laid: LaidNode): LaidNode[] => [
	laid,
	...laid.children.flatMap(flatten),
];

const findNode = (root: MindNode, id: string): MindNode | undefined =>
	root.id === id
		? root
		: root.children.map((c) => findNode(c, id)).find((x) => x !== undefined);

// ── 自定义节点卡片 ──────────────────────────────────────────
interface MindData extends Record<string, unknown> {
	nodeId: string;
	text: string;
	quote?: string;
	depth: number;
	side: Side | "root";
	childCount: number;
	collapsedHere: boolean;
	confirmed: boolean;
	foldIds: string[];
	onEdit: (id: string) => void;
	onAdd: (id: string) => void;
	onDelete: (id: string) => void;
	onToggle: (id: string) => void;
}

function MindNodeCard({ data, selected }: NodeProps<Node<MindData>>) {
	const {
		nodeId,
		text,
		quote,
		depth,
		side,
		childCount,
		collapsedHere,
		confirmed,
		foldIds,
		onEdit,
		onAdd,
		onDelete,
		onToggle,
	} = data;
	const isRoot = depth === 0;
	const cls = `mind-card depth-${Math.min(depth, 2)} ${side === "left" ? "side-left" : ""} ${selected ? "selected" : ""}`;
	return (
		<div className={cls} style={{ width: NODE_W, minHeight: NODE_H }}>
			{isRoot ? (
				<>
					<Handle
						type="source"
						id="r"
						position={Position.Right}
						className="mind-handle"
						isConnectable={false}
					/>
					<Handle
						type="source"
						id="l"
						position={Position.Left}
						className="mind-handle"
						isConnectable={false}
					/>
				</>
			) : side === "left" ? (
				<>
					<Handle
						type="target"
						position={Position.Right}
						className="mind-handle"
						isConnectable={false}
					/>
					<Handle
						type="source"
						position={Position.Left}
						className="mind-handle"
						isConnectable={false}
					/>
				</>
			) : (
				<>
					<Handle
						type="target"
						position={Position.Left}
						className="mind-handle"
						isConnectable={false}
					/>
					<Handle
						type="source"
						position={Position.Right}
						className="mind-handle"
						isConnectable={false}
					/>
				</>
			)}
			<div className="mind-card-text" title={text}>
				{text}
			</div>
			{quote !== undefined && (
				<div className="mind-card-quote" title={quote}>
					“{quote}”
				</div>
			)}
			{confirmed && depth > 0 && childCount === 0 && (
				<Tag className="mind-card-leaf">命题</Tag>
			)}
			{!confirmed && (
				<span
					className="mind-card-actions"
					onClick={(e) => e.stopPropagation()}
				>
					<Button
						type="text"
						size="small"
						icon={<EditOutlined />}
						title="重命名"
						onClick={() => onEdit(nodeId)}
					/>
					<Button
						type="text"
						size="small"
						icon={<PlusOutlined />}
						title="加子节点"
						onClick={() => onAdd(nodeId)}
					/>
					{!isRoot && (
						<Popconfirm
							title="删除该节点及其子树？"
							onConfirm={() => onDelete(nodeId)}
						>
							<Button
								type="text"
								size="small"
								danger
								icon={<DeleteOutlined />}
								title="删除"
							/>
						</Popconfirm>
					)}
				</span>
			)}
			{childCount > 0 && (
				<button
					type="button"
					className={`mind-fold ${collapsedHere ? "folded" : ""}`}
					title={collapsedHere ? `展开 ${childCount} 个子节点` : "折叠分支"}
					onClick={(e) => {
						e.stopPropagation();
						onToggle(nodeId);
					}}
					data-fold-ids={foldIds.join(",")}
				>
					{collapsedHere ? childCount : "−"}
				</button>
			)}
		</div>
	);
}

const nodeTypes = { mind: MindNodeCard };

// ── 页面 ────────────────────────────────────────────────────
function MindmapInner({ taskId, onBack, onConfirmed, autoGenerate }: Props) {
	const { message } = App.useApp();
	const flow = useReactFlow();
	const canvasRef = useRef<HTMLDivElement | null>(null);

	// 滚轮接管：滚轮=平移，cmd/ctrl+滚轮=缩放（RF 内建 wheel 模式不生效）
	useEffect(() => {
		const el = canvasRef.current;
		if (el === null) return undefined;
		return attachWheelPanZoom(el, flow);
	}, [flow]);
	const [state, setState] = useState<MindmapState | null>(null);
	const [loading, setLoading] = useState(false);
	const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
	const [renaming, setRenaming] = useState<{ id: string; val: string } | null>(
		null,
	);
	const [outlineOpen, setOutlineOpen] = useState(false);
	const generatedOnce = useRef(false);

	const load = useCallback(async () => {
		const r = await rpc("mindmap.get", { task_id: taskId });
		if (r.tree !== null && r.tree !== undefined) {
			setState({
				tree: r.tree as MindmapState["tree"],
				status: (r.status as string | null) ?? null,
			});
		}
	}, [taskId]);

	useEffect(() => {
		load().catch(() => {
			/* 尚无导图 — 空态 */
		});
	}, [load]);

	const generate = useCallback(async () => {
		setLoading(true);
		try {
			const r = await rpc("mindmap.generate", { task_id: taskId });
			setState({ tree: r.tree as MindmapState["tree"], status: "draft" });
			setCollapsed(new Set());
			message.success(
				`思维导图已生成（丢弃 ${r.dropped} 条未溯源内容，深度 ${r.depth}）`,
			);
		} catch (e) {
			message.error(String(e instanceof Error ? e.message : e));
		} finally {
			setLoading(false);
		}
	}, [taskId, message]);

	useEffect(() => {
		if (autoGenerate && !generatedOnce.current) {
			generatedOnce.current = true;
			void generate();
		}
	}, [autoGenerate, generate]);

	const edit = async (
		action: "rename" | "addChild" | "delete",
		nodeId: string,
		text?: string,
	) => {
		try {
			const r = await rpc("mindmap.editNode", {
				task_id: taskId,
				action,
				node_id: nodeId,
				text,
			});
			setState({ tree: r.tree as MindmapState["tree"], status: "draft" });
			if (action === "delete") {
				setCollapsed(
					(prev) => new Set([...prev].filter((id) => id !== nodeId)),
				);
			}
		} catch (e) {
			message.error(String(e instanceof Error ? e.message : e));
		}
	};

	const confirm = async () => {
		try {
			await rpc("mindmap.confirm", { task_id: taskId });
			message.success("已确认——叶子命题转为调研阶段，进入调研画布");
			setState((s) => (s === null ? s : { ...s, status: "confirmed" }));
			onConfirmed();
		} catch (e) {
			message.error(String(e instanceof Error ? e.message : e));
		}
	};

	const confirmed = state?.status === "confirmed";
	const root = state?.tree.root;

	const { nodes, edges, laidRoot, total } = useMemo(() => {
		if (root === undefined)
			return {
				nodes: [] as Node<MindData>[],
				edges: [] as Edge[],
				laidRoot: null,
				total: 0,
			};
		const { root: laid, count } = layoutBalanced(root, collapsed);
		const nodes: Node<MindData>[] = flatten(laid).map((l) => ({
			id: l.node.id,
			type: "mind",
			position: { x: l.x, y: l.y },
			width: NODE_W,
			height: NODE_H,
			data: {
				nodeId: l.node.id,
				text: l.node.text,
				quote: l.node.quote,
				depth: l.depth,
				side: l.side,
				childCount: l.node.children.length,
				collapsedHere: l.collapsedHere,
				confirmed,
				foldIds: l.node.children.map((c) => c.id),
				onEdit: (id: string) =>
					setRenaming({ id, val: findNode(root, id)?.text ?? "" }),
				onAdd: (id: string) => void edit("addChild", id, "新节点"),
				onDelete: (id: string) => void edit("delete", id),
				onToggle: (id: string) =>
					setCollapsed((prev) => {
						const next = new Set(prev);
						if (next.has(id)) next.delete(id);
						else next.add(id);
						return next;
					}),
			},
			draggable: false,
		}));
		const edges: Edge[] = [];
		const walkEdges = (l: LaidNode): void => {
			for (const c of l.children) {
				edges.push({
					id: `${l.node.id}->${c.node.id}`,
					source: l.node.id,
					target: c.node.id,
					// 根有两个 source 句柄（r/l），必须按分支方向指定
					sourceHandle:
						l.depth === 0 ? (c.side === "right" ? "r" : "l") : undefined,
					type: "default",
					style: { stroke: "#c6c6c6", strokeWidth: 1.5 },
				});
				walkEdges(c);
			}
		};
		walkEdges(laid);
		return { nodes, edges, laidRoot: laid, total: count };
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [root, collapsed, confirmed]);

	const outlineTreeData = useMemo(() => {
		const toAntd = (n: MindNode): DataNode => ({
			key: n.id,
			title: n.text,
			children: n.children.map(toAntd),
		});
		return root === undefined ? [] : [toAntd(root)];
	}, [root]);

	const centerNode = (id: string) => {
		if (laidRoot === null) return;
		const hit = flatten(laidRoot).find((l) => l.node.id === id);
		if (hit !== undefined) {
			void flow.setCenter(hit.x + NODE_W / 2, hit.y, {
				zoom: 1,
				duration: 400,
			});
		}
		setOutlineOpen(false);
	};

	return (
		<div className="mind-page">
			<div className="mind-toolbar">
				<Space>
					<Button icon={<ArrowLeftOutlined />} onClick={onBack}>
						回到对话
					</Button>
					<Typography.Title level={4} style={{ margin: 0 }}>
						思维导图
					</Typography.Title>
					{confirmed && <Tag color="green">已确认（冻结）</Tag>}
				</Space>
				<Space>
					{root !== undefined && (
						<Tooltip title="大纲模式（抽屉，点节点画布联动）">
							<Button
								icon={<UnorderedListOutlined />}
								onClick={() => setOutlineOpen(true)}
							>
								大纲
							</Button>
						</Tooltip>
					)}
					{root === undefined && (
						<Button
							type="primary"
							loading={loading}
							onClick={() => void generate()}
						>
							从对话生成思维导图
						</Button>
					)}
					{root !== undefined && !confirmed && (
						<Button type="primary" onClick={() => void confirm()}>
							确认，开始调研
						</Button>
					)}
				</Space>
			</div>
			<div className="mind-canvas" ref={canvasRef}>
				{root === undefined ? (
					<div className="mind-empty">
						{loading ? (
							<Spin size="large" tip="pi 会话提炼核心问题与分支结构……" />
						) : (
							<Empty description="点击上方按钮，从对话生成思维导图。每个节点带回查溯源（quote），确认前可编辑。" />
						)}
					</div>
				) : (
					<ReactFlow
						nodes={nodes}
						edges={edges}
						nodeTypes={nodeTypes}
						fitView
						minZoom={0.05}
						maxZoom={2}
						nodesDraggable={false}
						nodesConnectable={false}
						zoomOnScroll={false}
						panOnScroll={false}
						zoomOnPinch={false}
						proOptions={{ hideAttribution: true }}
					>
						<Background
							variant={BackgroundVariant.Dots}
							gap={22}
							size={1}
							color="#dcdcdc"
						/>
						<Controls showInteractive={false} position="bottom-right" />
						<MiniMap
							pannable
							zoomable
							position="bottom-left"
							style={{ width: 220, height: 140 }}
							maskColor="rgba(250,250,250,0.75)"
							nodeColor={(n) => {
								const d = (n.data as MindData | undefined)?.depth ?? 0;
								return d === 0 ? "#1c1c1c" : d === 1 ? "#9db9e8" : "#c9d8f5";
							}}
						/>
					</ReactFlow>
				)}
			</div>

			<Drawer
				title="大纲"
				placement="right"
				width={340}
				open={outlineOpen}
				onClose={() => setOutlineOpen(false)}
			>
				<Tree
					blockNode
					defaultExpandAll
					treeData={outlineTreeData}
					onSelect={(keys) => {
						if (keys.length > 0) centerNode(String(keys[0]));
					}}
				/>
			</Drawer>

			<Modal
				title="重命名节点"
				open={renaming !== null}
				onCancel={() => setRenaming(null)}
				footer={null}
				destroyOnHidden
			>
				{renaming !== null && (
					<Input
						autoFocus
						value={renaming.val}
						onChange={(e) => setRenaming({ ...renaming, val: e.target.value })}
						onPressEnter={() => {
							void edit("rename", renaming.id, renaming.val);
							setRenaming(null);
						}}
					/>
				)}
			</Modal>
		</div>
	);
}

export function MindmapPage(props: Props) {
	return (
		<ReactFlowProvider>
			<MindmapInner {...props} />
		</ReactFlowProvider>
	);
}
