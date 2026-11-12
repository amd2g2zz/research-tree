/** research-tree WebUI — chat hub 为唯一入口（用户裁定 2026-11-06）。
 * 对话对齐 ChatGPT 形态；思维导图/调研不做成 tab——
 * 在 chat 内确认后从 context 抽取脑图，脑图确认后进调研画布；
 * 回访入口 = 流内卡片。 */

import {
	ArrowUpOutlined,
	DeleteOutlined,
	EditOutlined,
	InboxOutlined,
	MoreOutlined,
	NodeIndexOutlined,
	PlusOutlined,
	SettingOutlined,
} from "@ant-design/icons";
import {
	App as AntApp,
	Button,
	Dropdown,
	Input,
	Layout,
	Modal,
	Select,
	Tag,
	Typography,
} from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectWs, onDelta, rest, rpc } from "./lib/rpc";
import type {
	ChatMsg,
	Kind,
	PiConfigSummary,
	Project,
	View,
} from "./lib/types";
import { MindmapPage } from "./views/MindmapPage";
import { ResearchPage } from "./views/ResearchPage";
import "./styles.scss";

const KINDS: Array<[Kind, string]> = [
	["auto", "自动"],
	["preference", "偏好"],
	["claim", "主张"],
	["guess", "猜测"],
	["branch", "岔路"],
];

/** 自动命名：第一句话提炼 5~15 字标题（去首尾标点，超长截断）。 */
export function clipTitle(text: string): string {
	const cleaned = text.trim().replace(/^[，。；！、\s]+|[，。；！\s]+$/g, "");
	if (cleaned.length <= 15) return cleaned === "" ? "未命名研究" : cleaned;
	return cleaned.slice(0, 15);
}

function Shell() {
	const { modal } = AntApp.useApp();
	const [projects, setProjects] = useState<Project[]>([]);
	const [taskId, setTaskId] = useState<string | null>(null);
	const [msgs, setMsgs] = useState<ChatMsg[]>([]);
	const [phase, setPhase] = useState<string>("chat");
	const [mindStatus, setMindStatus] = useState<string | null>(null);
	const [view, setView] = useState<View>("chat");
	const [autoGen, setAutoGen] = useState(false);
	const [draft, setDraft] = useState("");
	const [kind, setKind] = useState<Kind>("auto");
	const [busy, setBusy] = useState(false);
	const [thinking, setThinking] = useState(false);
	const [cot, setCot] = useState("");
	const [settledCot, setSettledCot] = useState<string | null>(null);
	const cotBuf = useRef("");
	const [piReady, setPiReady] = useState<PiConfigSummary | null>(null);
	const [showNew, setShowNew] = useState(false);
	const [newName, setNewName] = useState("");
	const [showSettings, setShowSettings] = useState(false);
	const [provider, setProvider] = useState("");
	const [apiKey, setApiKey] = useState("");
	const [modelId, setModelId] = useState("");
	// 侧栏管理（#704）：搜索 / 惰性加载 / 行内 重命名·归档·删除
	const [query, setQuery] = useState("");
	const [visibleCount, setVisibleCount] = useState(10);
	const [renameTarget, setRenameTarget] = useState<
		{ kind: "project" | "task"; id: string; initial: string } | null
	>(null);
	const [renameVal, setRenameVal] = useState("");

	const refresh = useCallback(async () => {
		const d = await rest<{ projects: Project[] }>("/api/tree");
		setProjects(d.projects);
	}, []);

	const refreshPi = useCallback(async () => {
		setPiReady(await rest<PiConfigSummary>("/api/config/pi"));
	}, []);

	const refreshHub = useCallback(async (tid: string) => {
		const h = await rpc("chat.history", { task_id: tid });
		setMsgs((h.messages ?? []) as ChatMsg[]);
		const s = await rpc("task.status", { task_id: tid });
		setPhase(String(s.phase ?? "chat"));
		const m = await rpc("mindmap.get", { task_id: tid });
		setMindStatus((m.status as string | null) ?? null);
	}, []);

	useEffect(() => {
		void refresh();
		void refreshPi();
	}, [refresh, refreshPi]);

	useEffect(() => {
		if (taskId !== null) void refreshHub(taskId);
	}, [taskId, refreshHub]);

	// 侧栏全文搜索（#704）：query 非空走服务端跨全库匹配，空则还原全列表
	useEffect(() => {
		if (query.trim() === "") {
			void refresh();
			return undefined;
		}
		const timer = setTimeout(() => {
			rest<{ projects: Project[] }>(
				`/api/projects/search?q=${encodeURIComponent(query.trim())}`,
			)
				.then((d) => setProjects(d.projects))
				.catch(() => {
					/* 搜索失败保持现列表 */
				});
		}, 300);
		return () => clearTimeout(timer);
	}, [query, refresh]);

	// 浏览器返回键 = 回对话（SPA 无路由，否则返回手势直接退出站点）
	useEffect(() => {
		const onPop = (): void => {
			setAutoGen(false);
			setView("chat");
		};
		window.addEventListener("popstate", onPop);
		return () => window.removeEventListener("popstate", onPop);
	}, []);

	useEffect(() => {
		if (view !== "chat") {
			window.history.pushState({ view }, "");
		}
	}, [view]);

	const send = useCallback(
		async (text: string, tidOverride?: string) => {
			const target = tidOverride ?? taskId;
			if (target === null || !text.trim()) return;
			setBusy(true);
			cotBuf.current = "";
			setCot("");
			setSettledCot(null);
			setThinking(true);
			try {
				if (kind === "auto") {
					onDelta((d) => {
						cotBuf.current += d;
						setCot(cotBuf.current);
					});
					await connectWs();
					await rpc("chat.turn", { task_id: target, text });
				} else {
					await connectWs();
					await rpc("chat.ingest", { task_id: target, text, kind });
				}
				setDraft("");
				await refreshHub(target);
				void refresh();
			} catch (e) {
				console.error(e);
				// 失败也要刷新——用户消息与错误行已先落账（#704）
				await refreshHub(target);
			} finally {
				setThinking(false);
				if (cotBuf.current !== "") setSettledCot(cotBuf.current);
				setCot("");
			}
		},
		[taskId, kind, refreshHub, refresh],
	);

	/** 首页即 chat 框（#704）：发送即建项目——标题=第一句话提炼 5~15 字，
	 * 默认 v0，随后直接进入该任务对话。 */
	const createAndSend = useCallback(
		async (text: string) => {
			if (!text.trim()) return;
			const pid = `p-${Date.now().toString(36)}`;
			await connectWs();
			await rpc("project.create", { project_id: pid, name: clipTitle(text) });
			await rpc("project.registerTask", {
				project_id: pid,
				task_id: `${pid}-main`,
				role: "main",
			});
			await refresh();
			setTaskId(`${pid}-main`);
			await send(text, `${pid}-main`);
		},
		[refresh, send],
	);

	/** 导航模型：对话是每个任务的门厅——切任务永远落在对话页；
	 * 画布（导图/调研）是深视图，必须显式进入。 */
	const selectTask = useCallback((id: string) => {
		setTaskId(id);
		setAutoGen(false);
		setView("chat");
	}, []);

	const create = useCallback(
		async (name: string) => {
			if (!name.trim()) return;
			const pid = `p-${Date.now().toString(36)}`;
			await connectWs();
			await rpc("project.create", { project_id: pid, name });
			await rpc("project.registerTask", {
				project_id: pid,
				task_id: `${pid}-main`,
				role: "main",
			});
			setNewName("");
			setShowNew(false);
			await refresh();
			setTaskId(`${pid}-main`);
		},
		[refresh],
	);

	const proj =
		projects.find((p) => p.lines.some((l) => l.task_id === taskId)) ?? null;
	const canResearch = phase === "research" || phase === "converged";
	// 导图卡门控（#704）：不再"有一条消息就绪"——由模型在最近一轮 reply 的
	// receipt 里判定的 converged 驱动（第一轮对话不诱导生成导图）
	const lastConverged = (() => {
		const replies = msgs.filter((m) => m.kind === "reply");
		const last = replies.at(-1);
		if (last?.receipt_json === null || last?.receipt_json === undefined)
			return false;
		try {
			return (
				(JSON.parse(last.receipt_json) as { converged?: boolean }).converged ===
				true
			);
		} catch {
			return false;
		}
	})();

	const openMindmap = (auto: boolean) => {
		setAutoGen(auto);
		setView("mindmap");
	};

	const doRename = async () => {
		if (renameTarget === null || !renameVal.trim()) return;
		if (renameTarget.kind === "project") {
			await rpc("project.rename", {
				project_id: renameTarget.id,
				name: renameVal.trim(),
			});
		} else {
			await rpc("task.rename", { task_id: renameTarget.id, title: renameVal.trim() });
		}
		setRenameTarget(null);
		setRenameVal("");
		await refresh();
	};

	const doArchiveProject = async (id: string) => {
		await rpc("project.archive", { project_id: id });
		await refresh();
	};

	const doDeleteProject = async (id: string) => {
		// 项目删除需先归档（服务端守卫）——一步到位：归档 + 删除
		await rpc("project.archive", { project_id: id });
		await rpc("project.delete", { project_id: id });
		await refresh();
	};

	const doArchiveTask = async (id: string) => {
		await rpc("task.archive", { task_id: id });
		await refresh();
	};

	const doDeleteTask = async (id: string) => {
		await rpc("task.archive", { task_id: id });
		await rpc("task.delete", { task_id: id });
		await refresh();
	};

	const rowMenu = (kind: "project" | "task", id: string, current: string): React.ReactElement => (
		<Dropdown
			menu={{
				items: [
					{
						key: "rename",
						icon: <EditOutlined />,
						label: "重命名",
						onClick: () => {
							setRenameTarget({ kind, id, initial: current });
							setRenameVal(current);
						},
					},
					{
						key: "archive",
						icon: <InboxOutlined />,
						label: "归档",
						onClick: () => {
							if (kind === "project") void doArchiveProject(id);
							else void doArchiveTask(id);
						},
					},
					{
						key: "delete",
						icon: <DeleteOutlined />,
						label: "删除",
						danger: true,
						onClick: () => {
							modal.confirm({
								title: "删除后无法恢复（将先归档再删除），确认？",
								okText: "删除",
								okButtonProps: { danger: true },
								onOk: () =>
									kind === "project" ? doDeleteProject(id) : doDeleteTask(id),
							});
						},
					},
				],
				onClick: ({ domEvent }) => {
					domEvent.stopPropagation();
				},
			}}
			trigger={["click"]}
		>
			<button
				type="button"
				className="row-menu"
				onClick={(e) => e.stopPropagation()}
			>
				<MoreOutlined />
			</button>
		</Dropdown>
	);

	return (
		<Layout className="app">
			<Layout.Sider width={260} theme="light" className="side">
				<div className="side-head">
					<button
						type="button"
						className="new-research-btn"
						onClick={() => setShowNew(true)}
					>
						<PlusOutlined />
						<span>新研究</span>
					</button>
					<Input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder="搜索项目、任务…"
						variant="filled"
						allowClear
						className="side-search"
					/>
				</div>
				<nav
					className="side-list"
					onScroll={(e) => {
						const el = e.currentTarget;
						if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
							setVisibleCount((c) => c + 10); // 惰性加载：滚到底部再取 10 条
						}
					}}
				>
					{projects
					.filter((p) => p.status !== "archived") // 归档项目不进活跃列表
					.slice(0, visibleCount)
					.map((p) => (
						<div key={p.project_id} className="proj-group">
							<div className="proj-row">
								<span className="proj-name">{p.name}</span>
								{rowMenu("project", p.project_id, p.name)}
							</div>
							{p.lines.map((l) => (
								<div key={l.task_id} className="task-line">
									<button
										type="button"
										className={`task-row ${l.task_id === taskId ? "active" : ""}`}
										onClick={() => selectTask(l.task_id)}
									>
										{l.role === "main" ? "◉" : "⑂"} {l.title ?? l.task_id}
										<Tag className="v-badge">v{p.vitals.latest?.v ?? 0}</Tag>
									</button>
									{rowMenu("task", l.task_id, l.title ?? l.task_id)}
								</div>
							))}
						</div>
					))}
					{projects.length > visibleCount && (
						<div className="side-more">继续滚动加载…</div>
					)}
				</nav>
				<div className="side-foot">
					<Button
						type="text"
						size="small"
						block
						icon={<SettingOutlined />}
						onClick={() => setShowSettings(true)}
					>
						<span
							className={`dot ${piReady?.keyed_session_ready ? "ok" : "off"}`}
						/>
						{piReady === null
							? "配置读取中…"
							: piReady.keyed_session_ready
								? "pi 已就绪"
								: "未配置 key"}
					</Button>
				</div>
			</Layout.Sider>
			<Layout.Content className="main">
				{taskId === null ? (
					<div className="home-hero">
						<Typography.Title level={3} style={{ marginBottom: 4 }}>
							research-tree
						</Typography.Title>
						<Typography.Text type="secondary">
							发送即创建研究：自动命名（5~15 字）、版本 v0，对话开始对齐。
						</Typography.Text>
						<div className="composer-pill home-composer">
							<Input
								value={draft}
								onChange={(e) => setDraft(e.target.value)}
								placeholder="把想法倒进来——例如：我想开个数据标注公司"
								onPressEnter={() => {
									if (draft.trim() && !busy) {
										void createAndSend(draft);
										setDraft("");
									}
								}}
								variant="borderless"
							/>
							<Button
								type="primary"
								shape="circle"
								icon={<ArrowUpOutlined />}
								className="send-circle"
								disabled={!draft.trim() || busy}
								onClick={() => {
									void createAndSend(draft);
									setDraft("");
								}}
							/>
						</div>
					</div>
				) : (
					<>
						<header className="topbar">
							{view !== "chat" ? (
								<Button
									type="text"
									size="small"
									className="topbar-home"
									onClick={() => {
										setAutoGen(false);
										setView("chat");
									}}
								>
									{proj?.name ?? "research-tree"}
								</Button>
							) : (
								<Typography.Title level={5} style={{ margin: 0 }}>
									{proj?.name ?? "research-tree"}
								</Typography.Title>
							)}
							<Tag>{phase}</Tag>
						</header>
						{view === "chat" && (
							<>
								<div className="stream">
									{msgs.map((m) =>
										m.role === "user" ? (
											<div key={m.seq} className="bubble user">
												{m.text}
											</div>
										) : m.kind === "reply" ? (
											<div key={m.seq} className="agent-msg">
												<div className="agent-text">{m.text}</div>
											</div>
										) : m.kind === "plan" ? (
											<div key={m.seq} className="plan-box">
												<div className="plan-title">研究计划草案</div>
												<pre>{m.text}</pre>
											</div>
										) : m.kind === "question" ? (
											<div key={m.seq} className="question-row">
												❓ {m.text}
											</div>
										) : m.kind === "recon" ? (
											<details key={m.seq} className="recon-box">
												<summary>🔎 {m.text.slice(0, 80)}</summary>
												<div>{m.text}</div>
											</details>
										) : m.kind === "error" ? (
											<div key={m.seq} className="error-row">
												⚠️ {m.text}
											</div>
										) : (
											<div key={m.seq} className="receipt-row">
												◉ {m.text}
											</div>
										),
									)}
									{settledCot !== null && !thinking && (
										<details className="cot-box">
											<summary>已深度思考</summary>
											<pre>{settledCot}</pre>
										</details>
									)}
									{thinking && (
										<div className="agent-msg typing">
											<div className="agent-label">rt · 思考中</div>
											{cot === "" ? (
												<div className="dots">
													<span />
													<span />
													<span />
												</div>
											) : (
												<pre className="cot-stream">{cot}</pre>
											)}
										</div>
									)}

									{/* 流内入口卡片：chat hub 是唯一导航入口（无 tab）。
											生成卡由模型判定的 converged 门控——第一轮对话
											不再诱导生成导图（#704 用户反馈） */}
									{mindStatus === null && lastConverged && !thinking && (
										<button
											type="button"
											className="hub-card"
											onClick={() => openMindmap(true)}
										>
											<NodeIndexOutlined className="hub-card-ico" />
											<span className="hub-card-main">
												<b>想法已成形——生成思维导图</b>
												<small>
													从对话 context 抽取总结脑图（quote 溯源，确认前可编辑）
												</small>
											</span>
										</button>
									)}
									{mindStatus === "draft" && (
										<button
											type="button"
											className="hub-card"
											onClick={() => openMindmap(false)}
										>
											<NodeIndexOutlined className="hub-card-ico" />
											<span className="hub-card-main">
												<b>思维导图草稿已生成</b>
												<small>打开画布查看、编辑并确认</small>
											</span>
										</button>
									)}
									{mindStatus === "confirmed" && (
										<button
											type="button"
											className="hub-card"
											onClick={() => setView("research")}
										>
											<NodeIndexOutlined className="hub-card-ico" />
											<span className="hub-card-main">
												<b>
													{canResearch
														? "调研画布进行中"
														: "调研画布（报告已冻结）"}
												</b>
												<small>打开 DAG 看板与人工裁决</small>
											</span>
										</button>
									)}

									{msgs.length === 0 && !thinking && (
										<div className="home-empty">
											把想法倒进来——研究从对话发起。
										</div>
									)}
								</div>
								<div className="composer">
									<div className="composer-pill">
										<Select
											value={kind}
											onChange={(v) => setKind(v)}
											className="kind-sel"
											popupMatchSelectWidth={false}
											options={KINDS.map(([k, label]) => ({
												value: k,
												label,
											}))}
										/>
										<Input
											value={draft}
											onChange={(e) => setDraft(e.target.value)}
											placeholder="追问、纠正、追加信息……"
											onPressEnter={() =>
												draft.trim() && !busy && void send(draft)
											}
											disabled={taskId === null}
											variant="borderless"
										/>
										<Button
											type="primary"
											shape="circle"
											icon={<ArrowUpOutlined />}
											className="send-circle"
											onClick={() => void send(draft)}
											disabled={!draft.trim() || busy || taskId === null}
										/>
									</div>
								</div>
							</>
						)}
						{view === "mindmap" && taskId !== null && (
							<MindmapPage
								taskId={taskId}
								autoGenerate={autoGen}
								onBack={() => {
									setAutoGen(false);
									setView("chat");
									void refreshHub(taskId);
								}}
								onConfirmed={() => {
									setAutoGen(false);
									void refreshHub(taskId).then(() => setView("research"));
								}}
							/>
						)}
						{view === "research" && taskId !== null && (
							<ResearchPage
								taskId={taskId}
								onBack={() => {
									setView("chat");
									void refreshHub(taskId);
								}}
								onOpenMindmap={() => setView("mindmap")}
							/>
						)}
					</>
				)}
			</Layout.Content>

			<Modal
				title="新研究"
				open={showNew}
				onCancel={() => setShowNew(false)}
				footer={null}
				destroyOnHidden
			>
				<Input
					autoFocus
					placeholder="研究主题（例如：我想开个数据标注公司）"
					value={newName}
					onChange={(e) => setNewName(e.target.value)}
					onPressEnter={() => void create(newName)}
				/>
				<div className="modal-actions">
					<Button onClick={() => setShowNew(false)}>取消</Button>
					<Button
						type="primary"
						onClick={() => void create(newName)}
						disabled={!newName.trim()}
					>
						建立研究
					</Button>
				</div>
			</Modal>

			<Modal
				title="pi 配置"
				open={showSettings}
				onCancel={() => setShowSettings(false)}
				footer={null}
				destroyOnHidden
			>
				<Typography.Paragraph type="secondary">
					key 写入 pi 自己的 models.json（与 pi agent 共用一份配置）；rt
					侧只记录 provider 名称，绝不回显密钥。
				</Typography.Paragraph>
				<Input
					placeholder="provider（如 openrouter）"
					value={provider}
					onChange={(e) => setProvider(e.target.value)}
				/>
				<Input.Password
					placeholder="API key"
					value={apiKey}
					onChange={(e) => setApiKey(e.target.value)}
					style={{ marginTop: 8 }}
				/>
				<Input
					placeholder="默认模型（可选，如 provider/model-id）"
					value={modelId}
					onChange={(e) => setModelId(e.target.value)}
					style={{ marginTop: 8 }}
				/>
				<div className="modal-actions">
					<Button
						onClick={async () => {
							await rpc("config.installExtensions", {});
							void refreshPi();
						}}
					>
						安装默认扩展
					</Button>
					<Button
						type="primary"
						disabled={!provider.trim() || !apiKey.trim()}
						onClick={async () => {
							try {
								await rpc("config.setProviderKey", {
									provider,
									api_key: apiKey,
									model_id: modelId || undefined,
								});
								if (modelId.trim())
									await rpc("config.setDefaultModel", { model: modelId });
								await refreshPi();
								setApiKey("");
								setShowSettings(false);
							} catch (e) {
								console.error(e);
							}
						}}
					>
					保存并验证
				</Button>
			</div>
		</Modal>

		<Modal
			title={renameTarget?.kind === "project" ? "重命名项目" : "重命名任务"}
			open={renameTarget !== null}
			onCancel={() => setRenameTarget(null)}
			footer={null}
			destroyOnHidden
		>
			<Input
				autoFocus
				value={renameVal}
				onChange={(e) => setRenameVal(e.target.value)}
				onPressEnter={() => void doRename()}
			/>
			<div className="modal-actions">
				<Button onClick={() => setRenameTarget(null)}>取消</Button>
				<Button type="primary" disabled={!renameVal.trim()} onClick={() => void doRename()}>
					保存
				</Button>
			</div>
		</Modal>
	</Layout>
);
}

export default function App() {
	return (
		<AntApp>
			<Shell />
		</AntApp>
	);
}
