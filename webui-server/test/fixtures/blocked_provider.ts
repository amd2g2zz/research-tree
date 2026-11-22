/** 可阻塞 fake DataSourceProvider（WS-F 基建，#742/#744 共用）：真实检索不可
 * 取消（#742 验收：stop 后如实上报、结果丢弃）——search 挂起至手工 release，
 * 机械构造"stop 于检索中→迟到完成被拒"；failNext 支持瞬时失败。 */

import type { DataSourceProvider } from "../../../rt-core/src/providers/types.js";

export interface FakeSource {
	title: string;
	url?: string;
	snippet?: string;
}

export interface BlockedProvider extends DataSourceProvider {
	/** 收到的全部 query（调用序） */
	queries: string[];
	/** 下一次 search 是否抛错（mirror research_worker.test.ts） */
	failNext: boolean;
	/** release = 释放一个挂起 search（FIFO）返回副本；pendingSearches = 在飞数 */
	release(): void;
	pendingSearches(): number;
}

export function createBlockedProvider(results: FakeSource[] = []): BlockedProvider {
	const queries: string[] = [];
	const pending: Array<() => void> = [];
	let failNext = false;
	const provider = {
		get failNext(): boolean {
			return failNext;
		},
		set failNext(v: boolean) {
			failNext = v;
		},
		get queries(): string[] {
			return queries;
		},
		async search({ query }: { query: string }): Promise<FakeSource[]> {
			queries.push(query);
			if (failNext) throw new Error("anysearch down");
			return new Promise<FakeSource[]>((resolve) => {
				pending.push(() => resolve(results.map((r) => ({ ...r }))));
			});
		},
		release: () => {
			const next = pending.shift();
			next?.();
		},
		pendingSearches: () => pending.length,
	};
	return provider as unknown as BlockedProvider;
}

/** 立即返回的 fake provider（对照组：其它任务不受扰测试用） */
export function createInstantProvider(results: FakeSource[] = [{ title: "来源A", url: "https://a.example", snippet: "摘要A" }]): DataSourceProvider {
	return {
		async search({ query }: { query: string }) {
			return results.map((r) => ({ ...r, title: `${r.title}：${query}` }));
		},
	} as DataSourceProvider;
}

/** 轮询条件成立（fixture 阻塞调用已派发）——不 sleep 猜时序（#742/#744 共用）。 */
export async function until(cond: () => boolean | Promise<boolean>, timeoutMs = 5000): Promise<void> {
	const start = Date.now();
	while (!(await cond())) {
		if (Date.now() - start > timeoutMs) throw new Error("condition not met within timeout");
		await new Promise((r) => setTimeout(r, 10));
	}
}
