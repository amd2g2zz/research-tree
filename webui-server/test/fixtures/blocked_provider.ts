/** 可阻塞 fake DataSourceProvider（WS-F fixture 基建，#742 与 #744 共用）。

真实检索（runRecon → provider.search）**不可取消**——#742 验收要求 stop 后
不可取消调用"如实上报、结果丢弃"。本 fixture 让 search 挂起直到测试手工
release，从而机械地构造"stop 于检索中 → 迟到完成被拒"的确定性场景。
同时支持瞬时失败（failNext，mirror research_worker.test.ts 的 anysearch down）。 */

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
	/** 释放一个挂起的 search（FIFO），返回 results 副本 */
	release(): void;
	/** 已派发且未释放的 search 数 */
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
