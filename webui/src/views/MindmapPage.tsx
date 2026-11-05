/** 确认阶段：全画布思维导图（issue #690；RPC 来自 #683）。
 * 生成（quote 溯源）→ 确认前可编辑（rename/addChild/delete）→ 确认冻结。 */

import {
	ArrowLeftOutlined,
	DeleteOutlined,
	EditOutlined,
	PlusOutlined,
} from "@ant-design/icons";
import {
	App,
	Button,
	Empty,
	Input,
	Popconfirm,
	Space,
	Spin,
	Tag,
	Tree,
	Typography,
} from "antd";
import type { DataNode } from "antd/es/tree";
import type { Key } from "react";
import { useCallback, useEffect, useState } from "react";
import { rpc } from "../lib/rpc";
import type { MindNode } from "../lib/types";

interface Props {
	taskId: string;
	onBack: () => void;
	onConfirmed: () => void;
}

interface MindmapState {
	tree: { root: MindNode };
	status: string | null;
}

const allKeys = (node: MindNode): Key[] => [
	node.id,
	...node.children.flatMap(allKeys),
];

export function MindmapPage({ taskId, onBack, onConfirmed }: Props) {
	const { message } = App.useApp();
	const [state, setState] = useState<MindmapState | null>(null);
	const [loading, setLoading] = useState(false);
	const [editingKey, setEditingKey] = useState<string | null>(null);
	const [editVal, setEditVal] = useState("");
	const [expanded, setExpanded] = useState<Key[]>([]);

	const load = useCallback(async () => {
		const r = await rpc("mindmap.get", { task_id: taskId });
		if (r.tree !== null && r.tree !== undefined) {
			const tree = r.tree as MindmapState["tree"];
			setState({ tree, status: (r.status as string | null) ?? null });
			setExpanded(allKeys(tree.root));
		}
	}, [taskId]);

	useEffect(() => {
		load().catch(() => {
			/* no mindmap yet — empty state */
		});
	}, [load]);

	const generate = async () => {
		setLoading(true);
		try {
			const r = await rpc("mindmap.generate", { task_id: taskId });
			const tree = r.tree as MindmapState["tree"];
			setState({ tree, status: "draft" });
			setExpanded(allKeys(tree.root));
			message.success(
				`思维导图已生成（丢弃 ${r.dropped} 条未溯源内容，深度 ${r.depth}）`,
			);
		} catch (e) {
			message.error(String(e instanceof Error ? e.message : e));
		} finally {
			setLoading(false);
		}
	};

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
			const tree = r.tree as MindmapState["tree"];
			setState({ tree, status: "draft" });
			if (action === "addChild") setExpanded((k) => [...k, nodeId]);
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

	const buildNode = (node: MindNode, depth: number): DataNode => {
		const confirmed = state?.status === "confirmed";
		const editing = editingKey === node.id;
		return {
			key: node.id,
			title: (
				<span className="mind-title">
					{editing ? (
						<Input
							size="small"
							style={{ width: 260 }}
							value={editVal}
							autoFocus
							onChange={(e) => setEditVal(e.target.value)}
							onPressEnter={() => {
								void edit("rename", node.id, editVal);
								setEditingKey(null);
							}}
							onBlur={() => {
								void edit("rename", node.id, editVal);
								setEditingKey(null);
							}}
						/>
					) : (
						<Space size={6}>
							<Typography.Text strong={depth === 0}>
								{node.text}
							</Typography.Text>
							{node.quote !== undefined && (
								<Typography.Text type="secondary" className="mind-quote">
									“{node.quote}”
								</Typography.Text>
							)}
						</Space>
					)}
					{!confirmed && !editing && (
						<span className="mind-actions">
							<Button
								type="text"
								size="small"
								icon={<EditOutlined />}
								onClick={() => {
									setEditingKey(node.id);
									setEditVal(node.text);
								}}
							/>
							<Button
								type="text"
								size="small"
								icon={<PlusOutlined />}
								onClick={() => void edit("addChild", node.id, "新节点")}
							/>
							<Popconfirm
								title="删除该节点及其子树？"
								onConfirm={() => void edit("delete", node.id)}
							>
								<Button
									type="text"
									size="small"
									danger
									icon={<DeleteOutlined />}
								/>
							</Popconfirm>
						</span>
					)}
					{confirmed && node.children.length === 0 && (
						<Tag className="mind-leaf-tag">命题</Tag>
					)}
				</span>
			),
			children: node.children.map((c) => buildNode(c, depth + 1)),
		};
	};

	const root = state?.tree.root;

	return (
		<div className="mind-page">
			<div className="mind-toolbar">
				<Space>
					<Button icon={<ArrowLeftOutlined />} onClick={onBack}>
						回到对话
					</Button>
					<Typography.Title level={4} style={{ margin: 0 }}>
						思维导图确认
					</Typography.Title>
					{state?.status === "confirmed" && (
						<Tag color="green">已确认（冻结）</Tag>
					)}
				</Space>
				<Space>
					{root === undefined && (
						<Button
							type="primary"
							loading={loading}
							onClick={() => void generate()}
						>
							从对话生成思维导图
						</Button>
					)}
					{root !== undefined && state?.status !== "confirmed" && (
						<Button type="primary" onClick={() => void confirm()}>
							确认，开始调研
						</Button>
					)}
				</Space>
			</div>
			<div className="mind-canvas">
				{root === undefined ? (
					<div className="mind-empty">
						{loading ? (
							<Spin size="large" tip="pi 会话提炼核心问题与分支结构……" />
						) : (
							<Empty description="点击右上角按钮，从对话生成思维导图。每个节点带回查溯源（quote），确认前可编辑。" />
						)}
					</div>
				) : (
					<Tree
						showLine={{ showLeafIcon: false }}
						blockNode
						expandedKeys={expanded}
						onExpand={(keys) => setExpanded(keys)}
						treeData={[buildNode(root, 0)]}
					/>
				)}
			</div>
		</div>
	);
}
