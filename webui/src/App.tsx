/** research-tree WebUI — chat hub 为唯一入口（用户裁定 2026-11-06）。
 * 对话对齐 ChatGPT 形态；思维导图/调研不做成 tab——
 * 在 chat 内确认后从 context 抽取脑图，脑图确认后进调研画布；
 * 回访入口 = 流内卡片。 */

import {
	ArrowUpOutlined,
	DeleteOutlined,
	EditOutlined,
	InboxOutlined,
	LinkOutlined,
	MoreOutlined,
	NodeIndexOutlined,
	PlusOutlined,
	SettingOutlined,
} from "@ant-design/icons";
import type { InputRef } from "antd";
import {
	Alert,
	App as AntApp,
	Badge,
	Button,
	Collapse,
	ConfigProvider,
	Dropdown,
	Input,
	Layout,
	Modal,
	Select,
	Skeleton,
	Tag,
	Tooltip,
	Typography,
} from "antd";
import "katex/dist/katex.min.css";
import {
	Fragment,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { renderMd } from "./lib/md";
import {
	connectWs,
	onDelta,
	onTurnEvent,
	onWsStatus,
	rest,
	rpc,
} from "./lib/rpc";
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

const PHASE_CN: Record<string, string> = {
	chat: "对话中",
	decompose: "待确认",
	research: "调研中",
	converged: "已收敛",
	committed: "已提交",
	paused: "已暂停",
};

/** 自动命名：第一句话提炼 5~15 字标题（去首尾标点，超长截断）。 */
export function clipTitle(text: string): string {
	const cleaned = text.trim().replace(/^[，。；！、\s]+|[，。；！\s]+$/g, "");
	if (cleaned.length <= 15) return cleaned === "" ? "未命名研究" : cleaned;
	return cleaned.slice(0, 15);
}

function Shell() {
	const { modal, message: messageApi } = AntApp.useApp();
	const [projects, setProjects] = useState<Project[]>([]);
	const [taskId, setTaskId] = useState<string | null>(null);
	const [msgs, setMsgs] = useState<ChatMsg[]>([]);
	const [phase, setPhase] = useState<string>("chat");
	const [mindStatus, setMindStatus] = useState<string | null>(null);
	const [view, setView] = useState<View>("chat");
	const [autoGen, setAutoGen] = useState(false);
	const [draft, setDraft] = useState("");
	const busyRef = useRef(false);
	const chatInputRef = useRef<InputRef>(null);
	const heroInputRef = useRef<InputRef>(null);
	const readChatDraft = (): string => chatInputRef.current?.input?.value ?? "";
	const clearChatDraft = (): void => {
		const input = chatInputRef.current?.input;
		if (input !== undefined && input !== null) input.value = "";
		setDraft("");
	};
	const readHeroDraft = (): string => heroInputRef.current?.input?.value ?? "";
	const clearHeroDraft = (): void => {
		const input = heroInputRef.current?.input;
		if (input !== undefined && input !== null) input.value = "";
		setDraft("");
	};
	const [kind, setKind] = useState<Kind>("auto");
	const [busy, setBusy] = useState(false);
	const [thinking, setThinking] = useState(false);
	const [cot, setCot] = useState("");
	const [settledCot, setSettledCot] = useState<string | null>(null);
	const [cotCollapsed, setCotCollapsed] = useState(false);
	const cotBuf = useRef("");
	const [piReady, setPiReady] = useState<PiConfigSummary | null>(null);
	const [wsStatus, setWsStatus] = useState<"connecting" | "open" | "closed">(
		"connecting",
	);

	// URL 与状态同步（#711）：可分享的 GET 地址；pushState 保留返回手势
	useEffect(() => {
		if (taskId === null) return;
		const hash = view === "chat" ? `#/t/${taskId}` : `#/t/${taskId}/${view}`;
		if (location.hash !== hash) {
			window.history.pushState({ taskId, view }, "", hash);
		}
	}, [taskId, view]);
	const [showNew, setShowNew] = useState(false);
	const [newName, setNewName] = useState("");
	const [showSettings, setShowSettings] = useState(false);
	const [provider, setProvider] = useState("");
	const [apiKey, setApiKey] = useState("");
	const [modelId, setModelId] = useState("");
	// 侧栏管理（#704）：搜索 / 惰性加载 / 行内 重命名·归档·删除
	const [query, setQuery] = useState("");
	const [visibleCount, setVisibleCount] = useState(10);
	const [renameTarget, setRenameTarget] = useState<{
		kind: "project" | "task";
		id: string;
		initial: string;
	} | null>(null);
	const [renameVal, setRenameVal] = useState("");

	const refresh = useCallback(async () => {
		const d = await rest<{ projects: Project[] }>("/api/tree");
		setProjects(d.projects);
	}, []);

	const refreshPi = useCallback(async () => {
		setPiReady(await rest<PiConfigSummary>("/api/config/pi"));
	}, []);

	const refreshHub = useCallback(async (tid: string) => {
		// busy 期间不覆盖流内乐观气泡（#720）——turn-end/finally 里的刷新兜底
		if (busyRef.current) return;
		const h = await rpc("chat.history", { task_id: tid });
		setMsgs((h.messages ?? []) as ChatMsg[]);
		// #716：进行中的 turn——恢复思考流（新客户端继续接收 turn-delta）
		const active = h.activeTurn as { thinking?: string } | null | undefined;
		if (
			active !== null &&
			active !== undefined &&
			active.thinking !== undefined &&
			active.thinking !== ""
		) {
			cotBuf.current = active.thinking;
			setCot(active.thinking);
			setThinking(true);
			setSettledCot(null);
		} else {
			setThinking(false);
		}
		const st = await rpc("task.status", { task_id: tid });
		setPhase(String(st.phase ?? "chat"));
		const m = await rpc("mindmap.get", { task_id: tid });
		setMindStatus((m.status as string | null) ?? null);
	}, []);

	useEffect(() => onWsStatus(setWsStatus), []);

	// turn 生命周期（#716）：turn-end 刷新落账消息；本任务的 turn-start 挂流
	useEffect(() => {
		return onTurnEvent((ev) => {
			if (taskId === null || ev.task_id !== taskId) return;
			if (ev.event === "turn-start") setThinking(true);
			if (ev.event === "turn-end") {
				setThinking(false);
				void refreshHub(taskId);
			}
		});
	}, [taskId, refreshHub]);

	useEffect(() => {
		void refresh();
		void refreshPi();
	}, [refresh, refreshPi]);

	useEffect(() => {
		if (taskId !== null) void refreshHub(taskId);
	}, [taskId, refreshHub]);

	// H5（#706 UX 审计）：进入/更新会话时定位最新消息（用户未上滚回看时）
	const streamRef = useRef<HTMLDivElement | null>(null);
	const pinnedBottom = useRef(true);
	useEffect(() => {
		pinnedBottom.current = true; // UX 备注1：切任务/切视图重新定位到最新
		const el = streamRef.current;
		if (el === null) return;
		if (pinnedBottom.current) el.scrollTop = el.scrollHeight;
	}, [msgs, view, taskId]);

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

	// hash 路由（#711）：#/t/:taskId(/:view) —— 每个 chat 任务都有 GET 可达
	// 的分享链接；刷新/返回/直接打开 URL 均恢复到该任务该视图
	useEffect(() => {
		const applyHash = (): void => {
			const m = /^#\/t\/([^/]+)(?:\/(mindmap|research))?/.exec(location.hash);
			if (m !== null) {
				setTaskId(decodeURIComponent(m[1]));
				setAutoGen(false);
				setView((m[2] as View) ?? "chat");
			} else {
				setAutoGen(false);
				setView("chat");
			}
		};
		if (location.hash !== "") applyHash();
		window.addEventListener("popstate", () => applyHash());
	}, []);

	const send = useCallback(
		async (text: string, tidOverride?: string) => {
			const target = tidOverride ?? taskId;
			if (target === null || !text.trim()) return;
			setBusy(true);
			busyRef.current = true;
			// 乐观渲染（#720）：用户气泡立即出现在流内——服务端在 turn 分发时
			// 落账同一条消息，refreshHub 同步时以服务端为准
			setMsgs((prev) => [
				...prev,
				{
					seq: -Date.now(),
					role: "user",
					kind: "text",
					text,
					receipt_json: null,
				} as ChatMsg,
			]);
			cotBuf.current = "";
			setCot("");
			setSettledCot(null);
			setThinking(true);
			try {
				if (kind === "auto") {
					onDelta((d) => {
						cotBuf.current += d;
						setCot(cotBuf.current);
						setThinking(true); // 刷新/换端后漏掉 turn-start 也能重新挂上
					});
					await connectWs();
					setDraft(""); // 服务端已先落账用户消息——发送即清（H4）
					await rpc("chat.turn", { task_id: target, text });
				} else {
					await connectWs();
					setDraft("");
					await rpc("chat.ingest", { task_id: target, text, kind });
				}
			} catch (e) {
				// 错误必须可见（#706 onboarding 死路：pi 未配置时静默失败）
				messageApi.error(String(e instanceof Error ? e.message : e));
				// UX 备注2：rpc 未达服务端时消息可能未落账——回填输入框可重发
				const input = chatInputRef.current?.input;
				if (input !== undefined && input !== null) input.value = text;
				// 失败也要刷新——用户消息与错误行已先落账（#704）
			} finally {
				busyRef.current = false;
				await refreshHub(target); // busy 已解除，此处刷新不会被守卫拦截
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
		async (text: string): Promise<boolean> => {
			if (!text.trim()) return false;
			try {
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
				return true;
			} catch (e) {
				// PM 备注1：建项目本身失败时第一句话不能无声丢失——草稿保留
				messageApi.error(String(e instanceof Error ? e.message : e));
				return false;
			}
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
	// B（#711）：最后一条 reply 的下标——思考块插入其上方
	const lastReplyIdx = msgs.reduce(
		(acc, m, i) => (m.kind === "reply" ? i : acc),
		-1,
	);
	// 导图门控（#713）：由模型在最近一轮 reply 的 receipt 里的 flow/blockers
	// 驱动——ready 才给入口；blocked 把原因逐条摆给用户
	const lastFlow = (() => {
		const replies = msgs.filter((m) => m.kind === "reply");
		const last = replies.at(-1);
		if (last?.receipt_json === null || last?.receipt_json === undefined)
			return {
				flow: "blocked" as "ready" | "blocked",
				userConfirmed: false,
				blockers: [] as string[],
			};
		try {
			const parsed = JSON.parse(last.receipt_json) as {
				flow?: string;
				userConfirmed?: boolean;
				blockers?: string[];
			};
			return {
				flow: parsed.flow === "ready" ? "ready" : "blocked",
				userConfirmed: parsed.userConfirmed === true,
				blockers: Array.isArray(parsed.blockers) ? parsed.blockers : [],
			};
		} catch {
			return {
				flow: "blocked" as "ready" | "blocked",
				blockers: [] as string[],
			};
		}
	})();
	// 问句只渲染最近一轮的（#713）
	const lastReplySeq = msgs.reduce(
		(acc, m) => (m.kind === "reply" ? Math.max(acc, m.seq) : acc),
		-1,
	);
	// 侦查消息归属到其后最近的 reply（#723：侦查/think 是 reply 的二级关系）
	const reconByReplySeq = useMemo(() => {
		const map = new Map<number, string[]>();
		let pending: string[] = [];
		for (const m of msgs) {
			if (m.kind === "recon") {
				pending.push(m.text);
			} else if (m.kind === "reply") {
				if (pending.length > 0) map.set(m.seq, pending);
				pending = [];
			}
		}
		return map;
	}, [msgs]);

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
			await rpc("task.rename", {
				task_id: renameTarget.id,
				title: renameVal.trim(),
			});
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

	const rowMenu = (
		kind: "project" | "task",
		id: string,
		current: string,
	): React.ReactElement => (
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
											{l.role === "main" ? "◉" : "⑂"}{" "}
											{l.title ?? (l.role === "main" ? p.name : l.task_id)}
											{p.vitals.latest !== null && (
												<Badge
													count={`v${p.vitals.latest.v}`}
													className="v-badge"
													color="#999"
												/>
											)}
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
								ref={heroInputRef}
								onChange={(e) => setDraft(e.target.value)}
								placeholder="把想法倒进来——例如：我想开个数据标注公司"
								onPressEnter={() => {
									const t = readHeroDraft();
									if (t.trim() && !busy) {
										clearHeroDraft();
										void createAndSend(t).then((ok) => {
											if (!ok) setDraft(t); // 失败回填可重发
										});
									}
								}}
								variant="borderless"
							/>
							<Button
								type="primary"
								shape="circle"
								icon={<ArrowUpOutlined />}
								className="send-circle"
								disabled={busy}
								onClick={() => {
									const t = readHeroDraft();
									if (t.trim() && !busy) {
										clearHeroDraft();
										void createAndSend(t).then((ok) => {
											if (!ok) setDraft(t); // 失败回填可重发
										});
									}
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
							{/* #734：主 UI = 纯聊天对话界面——三阶段 Steps 向导条是
									装饰性进度展示（导航入口本就在流内卡片），删除后
									对话流成为绝对主体 */}
							<Tooltip title="复制任务链接（可分享）">
								<Button
									type="text"
									size="small"
									icon={<LinkOutlined />}
									onClick={() => {
										void navigator.clipboard.writeText(location.href);
										void messageApi.success("任务链接已复制");
									}}
								/>
							</Tooltip>
							<Tooltip
								title={
									wsStatus === "open"
										? "已连接服务"
										: wsStatus === "connecting"
											? "连接中…"
											: "连接断开——自动重连中"
								}
							>
								<Badge
									status={
										wsStatus === "open"
											? "success"
											: wsStatus === "connecting"
												? "processing"
												: "error"
									}
								/>
							</Tooltip>
						</header>
						{view === "chat" && (
							<>
								<div
									className="stream"
									ref={streamRef}
									onScroll={(e) => {
										const el = e.currentTarget;
										pinnedBottom.current =
											el.scrollTop + el.clientHeight >= el.scrollHeight - 60;
									}}
								>
									{msgs.map((m, i) =>
										m.role === "user" ? (
											<div key={m.seq} className="bubble user">
												{m.text}
											</div>
										) : (
											<Fragment key={m.seq}>
												{/* B（#711）：思考块紧贴其回复上方——先思考后正文 */}
												{m.kind === "reply" &&
													i === lastReplyIdx &&
													(settledCot !== null ||
														(reconByReplySeq.get(m.seq) ?? []).length > 0) &&
													!thinking && (
														<Collapse
															className="cot-box"
															items={[
																...(settledCot !== null
																	? [
																			{
																				key: "cot",
																				label: "深度思考",
																				children: (
																					<div
																						className="md"
																						dangerouslySetInnerHTML={{
																							__html: renderMd(settledCot),
																						}}
																					/>
																				),
																			},
																		]
																	: []),
																...((reconByReplySeq.get(m.seq) ?? []).length >
																0
																	? [
																				{
																					key: "recon",
																					label: `前期侦查（${(reconByReplySeq.get(m.seq) ?? []).length} 条来源）`,
																					children: (
																						<div
																							className="md recon-md"
																							dangerouslySetInnerHTML={{
																								__html: renderMd(
																									(
																										reconByReplySeq.get(
																											m.seq,
																										) ?? []
																								)
																									.join("\n")
																									// 来源以「；N. 」编号分隔——在编号边界断行；
																									// 前缀「…来源：」后也断行，让首个编号落行首，
																									// marked 才能渲染成有序列表（title 内部的数字
																									// 不跟在"；/："后，不会误切）
																									.replace(/；(?=\d+\.\s)/g, "\n")
																									.replace(/：(?=\d+\.\s)/, "：\n"),
																								),
																							}}
																						/>
																					),
																				},
																		]
																	: []),
															]}
														/>
													)}
												{m.kind === "reply" ? (
													<div className="agent-msg">
														<div
															className="agent-text md"
															dangerouslySetInnerHTML={{
																__html: renderMd(m.text),
															}}
														/>
													</div>
												) : m.kind === "question" ? (
													m.seq > lastReplySeq ? (
														<button
															type="button"
															className="question-row"
															onClick={() => setDraft(m.text)}
															title="点击填入输入框"
														>
															❓ {m.text}
														</button>
													) : null
												) : m.kind === "recon" ? null : m.kind === "error" ? (
													<div className="error-row">
														<span className="row-ico">⚠️</span>
														<span
															className="md"
															dangerouslySetInnerHTML={{
																__html: renderMd(m.text),
															}}
														/>
													</div>
												) : (
													<div className="receipt-row">
														<span className="row-ico">◉</span>
														<span
															className="md"
															dangerouslySetInnerHTML={{
																__html: renderMd(m.text),
															}}
														/>
													</div>
												)}
											</Fragment>
										),
									)}
									{thinking && (
										<Collapse
											className="cot-live"
											activeKey={cotCollapsed ? [] : ["thinking"]}
											onChange={() => setCotCollapsed((c) => !c)}
											items={[
												{
													key: "thinking",
													label: "rt · 思考中",
													children:
														cot === "" ? (
															<div className="dots">
																<span />
																<span />
																<span />
															</div>
														) : (
															<div
																className="cot-stream md"
																dangerouslySetInnerHTML={{
																	__html: renderMd(cot),
																}}
															/>
														),
												},
											]}
										/>
									)}

									{/* 流内入口卡片（#713）：ready = 模型判定对齐充分，给生成入口；
											blocked = 把缺口逐条摆给用户——不再藏按钮也不空转 */}
									{mindStatus === null &&
										lastFlow.flow === "ready" &&
										!thinking && (
											<Alert
												className="flow-alert"
												type="success"
												showIcon
												message="对齐已充分——生成思维导图"
												description="从对话 context 抽取总结脑图（quote 溯源，确认前可编辑）"
												action={
													<Button
														size="small"
														type="primary"
														onClick={() => openMindmap(true)}
													>
														生成
													</Button>
												}
											/>
										)}
									{mindStatus === null &&
										lastFlow.flow === "blocked" &&
										lastFlow.userConfirmed &&
										lastFlow.blockers.length > 0 &&
										!thinking && (
											<Alert
												className="flow-alert"
												type="warning"
												showIcon
												message="进入调研前需要解决"
												description={
													<ul className="blockers-list">
														{lastFlow.blockers.map((b, i) => (
															<li key={`blk-${String(i)}`}>{b}</li>
														))}
													</ul>
												}
											/>
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
											ref={chatInputRef}
											onChange={(e) => setDraft(e.target.value)}
											placeholder="追问、纠正、追加信息……"
											onPressEnter={() => {
												const t = readChatDraft();
												if (t.trim() && !busy) {
													clearChatDraft();
													void send(t);
												}
											}}
											disabled={taskId === null}
											variant="borderless"
										/>
										<Button
											type="primary"
											shape="circle"
											icon={<ArrowUpOutlined />}
											className="send-circle"
											onClick={() => {
												const t = readChatDraft();
												if (t.trim() && !busy) {
													clearChatDraft();
													void send(t);
												}
											}}
											disabled={taskId === null}
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
					<Button
						type="primary"
						disabled={!renameVal.trim()}
						onClick={() => void doRename()}
					>
						保存
					</Button>
				</div>
			</Modal>
		</Layout>
	);
}

export default function App() {
	return (
		// M1（#706 UX 审计）：antd 默认蓝 #1677ff 与自定义 #2f6fed 双主蓝并存
		// borderRadiusLG: 12 = M6 设置弹窗圆角与全局体系一致
		<ConfigProvider
			theme={{ token: { colorPrimary: "#2f6fed", borderRadiusLG: 12 } }}
		>
			<AntApp>
				<Shell />
			</AntApp>
		</ConfigProvider>
	);
}
