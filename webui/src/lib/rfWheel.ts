import type { ReactFlowInstance } from "@xyflow/react";

/** XMind 滚轮形态：滚轮=平移，cmd/ctrl+滚轮=缩放。
 * React Flow 内建 wheel 模式（panOnScroll/zoomOnScroll）在本环境不生效
 * （pane 未挂 wheel 行为），由本函数接管：passive:false 才能 preventDefault
 * 拦下浏览器默认滚动/缩放。zoom 边界与画布 minZoom/maxZoom 一致。 */
export function attachWheelPanZoom(
	el: HTMLElement,
	flow: Pick<ReactFlowInstance, "getViewport" | "setViewport" | "getZoom" | "zoomTo">,
): () => void {
	const MIN_ZOOM = 0.05;
	const MAX_ZOOM = 2;
	const onWheel = (e: WheelEvent): void => {
		e.preventDefault();
		if (e.ctrlKey || e.metaKey) {
			const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
			const next = Math.min(Math.max(flow.getZoom() * factor, MIN_ZOOM), MAX_ZOOM);
			void flow.zoomTo(next, { duration: 80 });
		} else {
			const vp = flow.getViewport();
			flow.setViewport({ x: vp.x - e.deltaX, y: vp.y - e.deltaY, zoom: vp.zoom });
		}
	};
	el.addEventListener("wheel", onWheel, { passive: false });
	return () => el.removeEventListener("wheel", onWheel);
}
