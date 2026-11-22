/** 脚本化 fake pi runner（WS-F 基建，#742/#744 共用）——数据+脚本而非 mock
 * 框架（plan §5），断言行为非 stub。脚本每次调用消费一项：string 原样返回；
 * object JSON 化；{block:true} 挂起至 release()；{slowMs,then} 延迟；{error}
 * reject；耗尽走 defaultResponse。 */

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
	/** 释放挂起的阻塞调用（FIFO）；无挂起 no-op；pendingBlocks = 在飞阻塞数 */
	release(): void;
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
