/** research-tree WebUI — chat hub 为唯一入口（用户裁定 2026-11-06）。
 * 对话对齐 ChatGPT 形态；思维导图/调研不做成 tab——
 * 在 chat 内确认后从 context 抽取脑图，脑图确认后进调研画布；
 * 回访入口 = 流内卡片。 */

import {
	ArrowUpOutlined,
	NodeIndexOutlined,
	PlusOutlined,
	SettingOutlined,
} from "@ant-design/icons";
import {
	App as AntApp,
	Button,
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

function Shell() {
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

	const send = useCallback(
		async (text: string) => {
			if (taskId === null || !text.trim()) return;
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
					await rpc("chat.turn", { task_id: taskId, text });
				} else {
					await connectWs();
					await rpc("chat.ingest", { task_id: taskId, text, kind });
				}
				setDraft("");
				await refreshHub(taskId);
			} catch (e) {
				console.error(e);
			} finally {
				setThinking(false);
				if (cotBuf.current !== "") setSettledCot(cotBuf.current);
				setCot("");
			}
		},
		[taskId, kind, refreshHub],
	);

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

	const openMindmap = (auto: boolean) => {
		setAutoGen(auto);
		setView("mindmap");
	};

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
				</div>
				<nav className="side-list">
					{projects.map((p) => (
						<div key={p.project_id} className="proj-group">
							<div className="proj-row">{p.name}</div>
							{p.lines.map((l) => (
								<button
									type="button"
									key={l.task_id}
									className={`task-row ${l.task_id === taskId ? "active" : ""}`}
									onClick={() => setTaskId(l.task_id)}
								>
									{l.role === "main" ? "◉" : "⑂"} {l.task_id}
								</button>
							))}
						</div>
					))}
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
					<div className="home-empty">
						<Typography.Title level={3}>research-tree</Typography.Title>
						<Typography.Text type="secondary">
							把想法倒进来——研究从对话发起，经思维导图确认，落为可执行调研。
						</Typography.Text>
					</div>
				) : (
					<>
						<header className="topbar">
							<Typography.Title level={5} style={{ margin: 0 }}>
								{proj?.name ?? "research-tree"}
							</Typography.Title>
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
										) : m.kind === "question" ? (
											<div key={m.seq} className="question-row">
												❓ {m.text}
											</div>
										) : m.kind === "recon" ? (
											<details key={m.seq} className="recon-box">
												<summary>🔎 {m.text.slice(0, 80)}</summary>
												<div>{m.text}</div>
											</details>
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

									{/* 流内入口卡片：chat hub 是唯一导航入口（无 tab） */}
									{mindStatus === null && msgs.length > 0 && !thinking && (
										<button
											type="button"
											className="hub-card"
											onClick={() => openMindmap(true)}
										>
											<NodeIndexOutlined className="hub-card-ico" />
											<span className="hub-card-main">
												<b>上下文已就绪——生成思维导图</b>
												<small>
													确认后从对话 context 抽取脑图（quote
													溯源，确认前可编辑）
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
