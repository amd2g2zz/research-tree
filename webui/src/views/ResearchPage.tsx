/** 调研画布页（issue #690）：stages DAG 分层展示 + 人工裁决冻结。
 * 数据源 /api/research/:taskId（#559 三层投影 + parallel_stages 表），
 * engine 事件驱动刷新。 */

import { ArrowLeftOutlined, ReloadOutlined } from "@ant-design/icons";
import {
	App,
	Button,
	Card,
	Empty,
	Select,
	Space,
	Spin,
	Tag,
	Typography,
} from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { onEngine, rest, rpc } from "../lib/rpc";
import type { ResearchView, StageInfo } from "../lib/types";

interface Props {
	taskId: string;
	onBack: () => void;
}

const VERDICTS = ["GO", "NO-GO", "PARK", "REFRAMED"] as const;

const STAGE_TAG: Record<string, { color: string; label: string }> = {
	pending: { color: "default", label: "待执行" },
	ready: { color: "blue", label: "就绪" },
	running: { color: "processing", label: "执行中" },
	done: { color: "green", label: "完成" },
	failed: { color: "red", label: "失败" },
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
				return parent === undefined ? max : Math.max(max, depthOf(parent) + 1);
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

export function ResearchPage({ taskId, onBack }: Props) {
	const { message } = App.useApp();
	const [view, setView] = useState<ResearchView | null>(null);
	const [loading, setLoading] = useState(true);
	const [verdict, setVerdict] = useState<string>("GO");
	const reloadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
		onEngine(scheduleReload)
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

	const freeze = async () => {
		try {
			const r = await rpc("research.freeze", { task_id: taskId, verdict });
			message.success(`裁决 ${r.verdict} 已签署，v${r.v} 已提交`);
			void load();
		} catch (e) {
			message.error(String(e instanceof Error ? e.message : e));
		}
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

	const columns = view === null ? [] : layer(view.stages);
	const stageTag = (status: string) =>
		STAGE_TAG[status] ?? { color: "default", label: status };

	return (
		<div className="research-page">
			<div className="research-toolbar">
				<Space>
					<Button icon={<ArrowLeftOutlined />} onClick={onBack}>
						回到对话
					</Button>
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
			<div className="dag-canvas">
				{columns.length === 0 ? (
					<Empty description="暂无调研阶段——回到思维导图确认后会机械展开为阶段 DAG。" />
				) : (
					columns.map((col, i) => (
						<div key={`layer-${String(i)}`} className="dag-column">
							<div className="dag-layer-label">第 {i + 1} 层</div>
							{col.map((s) => {
								const t = stageTag(s.status);
								return (
									<Card
										key={s.stage_id}
										size="small"
										className="dag-card"
										title={s.title}
										extra={<Tag color={t.color}>{t.label}</Tag>}
									>
										<Typography.Text type="secondary" className="dag-meta">
											{s.claim_ids.length} 个命题 · 依赖 {s.depends_on.length}
										</Typography.Text>
									</Card>
								);
							})}
						</div>
					))
				)}
			</div>
		</div>
	);
}
