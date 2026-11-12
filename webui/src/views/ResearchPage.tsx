/** 调研画布页（issue #694）：主区 = React Flow DAG（stage 节点 + depends_on
 * 连线），底部 = 引擎事件 console（实时流）。数据源 /api/research/:taskId
 * （#559 三层投影 + parallel_stages 表），人工裁决冻结。 */

import "@xyflow/react/dist/style.css";
import {
	Background,
	BackgroundVariant,
	Controls,
	Handle,
	MiniMap,
	Position,
	ReactFlow,
	ReactFlowProvider,
	type Edge,
	type Node,
	type NodeProps,
	useReactFlow,
} from "@xyflow/react";
import {
	ArrowLeftOutlined,
	NodeIndexOutlined,
	ReloadOutlined,
} from "@ant-design/icons";
import { App, Button, Empty, Select, Space, Spin, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { onEngine, rest, rpc } from "../lib/rpc";
import { attachWheelPanZoom } from "../lib/rfWheel";
import type { ResearchView, StageInfo } from "../lib/types";

interface Props {
	taskId: string;
	onBack: () => void;
	/** 回看已确认的思维导图（冻结树只读） */
	onOpenMindmap?: () => void;
}

const VERDICTS = ["GO", "NO-GO", "PARK", "REFRAMED"] as const;

const STAGE_TAG: Record<string, { color: string; bg: string; label: string }> = {
	pending: { color: "default", bg: "#f0f0f0", label: "待执行" },
	ready: { color: "blue", bg: "#dbe8ff", label: "就绪" },
	running: { color: "processing", bg: "#d6f0ff", label: "执行中" },
	done: { color: "green", bg: "#d9f2dd", label: "完成" },
	failed: { color: "red", bg: "#ffdbdb", label: "失败" },
};

/** Kahn 分层：depends_on 决定列；环/缺失依赖回退单列（数据来自机械计划，正常无环）。 */
function layer(stages: StageInfo[]): StageInfo[][] {
	const byId = new Map(stages.map((s) => [s.stage_id, s]));
	const depth = new Map<string, number>();
	const visiting = new Set<string>();
	const depthOf = (s: StageInfo): number => {
		const cached = depth.get(s.stage_id);
		if (cached !== undefined) return cached;
		if (visiting.has(s.stage_id)) return 0; // cycle guard
		visiting.add(s.stage_id);
		const d =
			s.depends_on.reduce((max, dep) => {
				const parent = byId.get(dep);
				return parent === undefined
					? max
					: Math.max(max, depthOf(parent) + 1);
			}, -1) + 1;
		visiting.delete(s.stage_id);
		depth.set(s.stage_id, d);
		return d;
	};
	const columns: StageInfo[][] = [];
	for (const s of stages) {
		const d = depthOf(s);
		if (columns[d] === undefined) columns[d] = [];
		columns[d].push(s);
	}
	return columns.filter((c) => c !== undefined);
}

function questionText(view: ResearchView): string {
	if (typeof view.question === "string") return view.question;
	if (
		view.question !== null &&
		typeof view.question === "object" &&
		"text" in view.question
	) {
		return String((view.question as { text?: unknown }).text ?? "");
	}
	return "";
}

// ── DAG 节点卡 ──────────────────────────────────────────────
const STAGE_W = 264;
const STAGE_H = 96;
const DGAP_X = 96;
const DGAP_Y = 30;

interface StageData extends Record<string, unknown> {
	title: string;
	status: string;
	claims: number;
	depends: number;
}

function StageNodeCard({ data }: NodeProps<Node<StageData>>) {
	const t = STAGE_TAG[data.status] ?? {
		color: "default",
		bg: "#f0f0f0",
		label: data.status,
	};
	return (
		<div
			className="dag-node"
			style={{ width: STAGE_W, minHeight: STAGE_H }}
		>
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
			<div className="dag-node-head">
				<span className="dag-node-title" title={data.title}>
					{data.title}
				</span>
				<span className="dag-node-tag" style={{ background: t.bg }}>
					{t.label}
				</span>
			</div>
			<div className="dag-node-meta">
				{data.claims} 个命题 · 依赖 {data.depends}
			</div>
		</div>
	);
}

const stageNodeTypes = { stage: StageNodeCard };

function DagInner({ view }: { view: ResearchView }) {
	const flow = useReactFlow();
	const wheelRef = useRef<HTMLDivElement | null>(null);

	// 滚轮接管：滚轮=平移，cmd/ctrl+滚轮=缩放（RF 内建 wheel 模式不生效）
	useEffect(() => {
		const el = wheelRef.current;
		if (el === null) return undefined;
		return attachWheelPanZoom(el, flow);
	}, [flow]);

	const { nodes, edges } = useMemo(() => {
		const cols = layer(view.stages);
		const mkNode = (s: StageInfo, x: number, y: number): Node<StageData> => ({
			id: s.stage_id,
			type: "stage",
			position: { x, y },
			width: STAGE_W,
			height: STAGE_H,
			data: {
				title: s.title,
				status: s.status,
				claims: s.claim_ids.length,
				depends: s.depends_on.length,
			},
			draggable: false,
		});
		let nodes: Node<StageData>[];
		if (cols.length <= 1) {
			// 无依赖边：单层网格铺开（5 列），不是一条竖列
			const flat = cols[0] ?? [];
			const perRow = 5;
			const rows = Math.ceil(flat.length / perRow);
			nodes = flat.map((s, i) =>
				mkNode(
					s,
					(i % perRow) * (STAGE_W + DGAP_X),
					Math.floor(i / perRow) * (STAGE_H + DGAP_Y) -
						((rows - 1) * (STAGE_H + DGAP_Y)) / 2,
				),
			);
		} else {
			// 多层：层 = 列，层内纵向堆叠并居中
			nodes = cols.flatMap((col, li) => {
				const colH = col.length * (STAGE_H + DGAP_Y) - DGAP_Y;
				const y0 = -colH / 2;
				return col.map((s, si) =>
					mkNode(
						s,
						li * (STAGE_W + DGAP_X),
						y0 + si * (STAGE_H + DGAP_Y),
					),
				);
			});
		}
		const ids = new Set(view.stages.map((s) => s.stage_id));
		const edges: Edge[] = [];
		for (const s of view.stages) {
			for (const dep of s.depends_on) {
				if (ids.has(dep)) {
					edges.push({
						id: `${dep}->${s.stage_id}`,
						source: dep,
						target: s.stage_id,
						type: "default",
						style: { stroke: "#b9c2d0", strokeWidth: 1.5 },
					});
				}
			}
		}
		return { nodes, edges };
	}, [view]);

	return (
		<div className="dag-wheel" ref={wheelRef}>
			<ReactFlow
				nodes={nodes}
				edges={edges}
				nodeTypes={stageNodeTypes}
				fitView
				minZoom={0.1}
				maxZoom={1.6}
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
				style={{ width: 200, height: 120 }}
				maskColor="rgba(250,250,250,0.75)"
				nodeColor={(n) => {
					const st = (n.data as StageData | undefined)?.status ?? "pending";
					return st === "done"
						? "#52c41a"
						: st === "running"
							? "#2f9bed"
							: st === "failed"
								? "#e05252"
								: "#9db9e8";
				}}
			/>
			</ReactFlow>
		</div>
	);
}

export function ResearchPage({ taskId, onBack, onOpenMindmap }: Props) {
	const { message, modal } = App.useApp();
	const [view, setView] = useState<ResearchView | null>(null);
	const [loading, setLoading] = useState(true);
	const [verdict, setVerdict] = useState<string>("GO");
	const [consoleLines, setConsoleLines] = useState<string[]>([]);
	const reloadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
	const consoleRef = useRef<HTMLDivElement | null>(null);

	const load = useCallback(async () => {
		try {
			const v = await rest<ResearchView>(
				`/api/research/${encodeURIComponent(taskId)}`,
			);
			setView(v);
		} catch (e) {
			message.error(String(e instanceof Error ? e.message : e));
		} finally {
			setLoading(false);
		}
	}, [taskId, message]);

	const scheduleReload = useCallback(() => {
		if (reloadTimer.current !== null) clearTimeout(reloadTimer.current);
		reloadTimer.current = setTimeout(() => void load(), 400);
	}, [load]);

	useEffect(() => {
		void load();
		let off: (() => void) | undefined;
		onEngine((line) => {
			setConsoleLines((prev) => [...prev.slice(-499), line]);
			scheduleReload();
		})
			.then((unsub) => {
				off = unsub;
			})
			.catch(() => {
				/* ws 未连上时靠 load() 的首次拉取 */
			});
		return () => {
			off?.();
			if (reloadTimer.current !== null) clearTimeout(reloadTimer.current);
		};
	}, [load, scheduleReload]);

	useEffect(() => {
		const el = consoleRef.current;
		if (el !== null) el.scrollTop = el.scrollHeight;
	}, [consoleLines]);

	const freeze = () => {
		// P1-2：冻结是不可逆提交（append-only）——弹确认，展示裁决与后果
		modal.confirm({
			title: `冻结裁决：${verdict}`,
			content:
				"版本 append-only，提交后不可撤销。此操作将当前调研快照签署为正式版本并回到对话阶段。",
			okText: "签署并提交",
			okButtonProps: { danger: true },
			onOk: async () => {
				try {
					const r = await rpc("research.freeze", { task_id: taskId, verdict });
					message.success(`裁决 ${r.verdict} 已签署，v${r.v} 已提交`);
					setConsoleLines((prev) => [
						...prev,
						`[human] 冻结裁决 ${r.verdict} — v${r.v} 提交`,
					]);
					void load();
				} catch (e) {
					message.error(String(e instanceof Error ? e.message : e));
				}
			},
		});
	};

	if (loading && view === null) {
		return (
			<div className="research-page">
				<div className="research-empty">
					<Spin size="large" />
				</div>
			</div>
		);
	}

	return (
		<div className="research-page">
			<div className="research-toolbar">
				<Space>
					<Button icon={<ArrowLeftOutlined />} onClick={onBack}>
						回到对话
					</Button>
					{onOpenMindmap !== undefined && (
						<Button icon={<NodeIndexOutlined />} onClick={onOpenMindmap}>
							思维导图
						</Button>
					)}
					<Typography.Title level={4} style={{ margin: 0 }}>
						调研画布
					</Typography.Title>
					{view !== null && questionText(view) !== "" && (
						<Typography.Text type="secondary">
							研究问题：{questionText(view)}
						</Typography.Text>
					)}
				</Space>
				<Space>
					<Button icon={<ReloadOutlined />} onClick={() => void load()} />
					<Select
						value={verdict}
						onChange={setVerdict}
						style={{ width: 130 }}
						options={VERDICTS.map((v) => ({ value: v, label: v }))}
					/>
					<Button type="primary" onClick={() => void freeze()}>
						冻结裁决
					</Button>
				</Space>
			</div>
			<div className="dag-flow">
				{view === null || view.stages.length === 0 ? (
					<Empty
						style={{ paddingTop: "18vh" }}
						description="暂无调研阶段——回到思维导图确认后会机械展开为阶段 DAG。"
					/>
				) : (
					<ReactFlowProvider>
						<DagInner view={view} />
					</ReactFlowProvider>
				)}
			</div>
			<div className="research-console" ref={consoleRef}>
				{consoleLines.length === 0 ? (
					<div className="rc-line rc-dim">── 引擎事件流（实时）──</div>
				) : (
					consoleLines.map((l, i) => (
						<div key={`rc-${String(i)}`} className="rc-line">
							{l}
						</div>
					))
				)}
			</div>
		</div>
	);
}
