/** 脚本化 fake pi runner（WS-F fixture 基建，#742 与 #744 共用）。

原则（plan §5 WS-F）：fixture 是数据+脚本，不是 mock 框架——照既有
mkdtemp+依赖注入风格（pi_extensions.test.ts 的 installer 注入），测试
持引用手工释放阻塞调用，断言行为而非断言 stub。

可编程响应序列：每次调用消费脚本的下一项：
- string                     → 原样返回（文本）
- Record<string, unknown>    → JSON.stringify 返回
- { block: true }            → 挂起不返回，直到 release()（stop 竞态/迟到完成测试）
- { slowMs, then }           → 延迟后返回（事件循环不冻结证明等）
- { error: string }          → reject（综合失败路径）
- 脚本耗尽                   → 兜底 defaultResponse */

export type ScriptedResponse =
	| string
	| Record<string, unknown>
	| { block: true }
	| { slowMs: number; then: string | Record<string, unknown> }
	| { error: string };

export interface FakePiRunner {
	/** 注入 WorkerDeps.piRunner / server options.piRunner 的可调用体 */
	runner: (command: string, prompt: string) => Promise<string>;
	/** 收到的全部 prompt（调用序） */
	calls: string[];
	/** 释放挂起的阻塞调用（FIFO）；无挂起时 no-op */
	release(): void;
	/** 已派发且未释放的阻塞调用数 */
	pendingBlocks(): number;
}

export function createFakePiRunner(
	script: ScriptedResponse[],
	defaultResponse: ScriptedResponse = {
		findings: "兜底综合发现（fixture 默认）",
		relevance: 0.7,
		coverage: 0.7,
	},
): FakePiRunner {
	const isObj = (x: ScriptedResponse): x is Record<string, unknown> =>
		typeof x === "object" && x !== null && !Array.isArray(x);
	const calls: string[] = [];
	const pending: Array<() => void> = [];
	let cursor = 0;
	const runner = (command: string, prompt: string): Promise<string> => {
		void command;
		calls.push(prompt);
		const item: ScriptedResponse = cursor < script.length ? script[cursor]! : defaultResponse;
		cursor += 1;
		if (typeof item === "string") return Promise.resolve(item);
		if (!isObj(item)) return Promise.resolve(JSON.stringify(item));
		const obj = item as Record<string, unknown>;
		if (obj.block === true) {
			return new Promise<string>((resolve) => {
				pending.push(() => resolve(JSON.stringify(defaultResponse)));
			});
		}
		if (typeof obj.slowMs === "number") {
			const slowMs = obj.slowMs;
			const then = obj.then;
			return new Promise<string>((resolve) => {
				setTimeout(() => resolve(typeof then === "string" ? then : JSON.stringify(then)), slowMs);
			});
		}
		if (typeof obj.error === "string") {
			return Promise.reject(new Error(obj.error));
		}
		return Promise.resolve(JSON.stringify(item));
	};
	return {
		runner,
		calls,
		release: () => {
			const next = pending.shift();
			next?.();
		},
		pendingBlocks: () => pending.length,
	};
}
