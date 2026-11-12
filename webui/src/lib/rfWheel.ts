import type { ReactFlowInstance } from "@xyflow/react";

/** 滚轮=以指针为锚缩放（放大缩小），平移=拖拽画布。
 * React Flow 内建 wheel 模式（panOnScroll/zoomOnScroll/zoomOnPinch）在本环境
 * 不生效（pane 未挂 wheel 行为），由本函数接管：passive:false 才能
 * preventDefault 拦下浏览器默认滚动/缩放。缩放边界与画布 minZoom/maxZoom 一致，
 * 指针锚定保持光标下的图坐标不动。 */
export function attachWheelPanZoom(
	el: HTMLElement,
	flow: Pick<ReactFlowInstance, "getViewport" | "setViewport" | "getZoom">,
): () => void {
	const MIN_ZOOM = 0.05;
	const MAX_ZOOM = 2;
	const ZOOM_STEP = 1.12;
	const onWheel = (e: WheelEvent): void => {
		e.preventDefault();
		const next = Math.min(
			Math.max(
				flow.getZoom() * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP),
				MIN_ZOOM,
			),
			MAX_ZOOM,
		);
		const rect = el.getBoundingClientRect();
		const px = e.clientX - rect.left;
		const py = e.clientY - rect.top;
		const vp = flow.getViewport();
		const ratio = next / vp.zoom;
		// 锚定指针：screen = flow*zoom + offset → offset' = p - (p-offset)*ratio
		flow.setViewport({
			x: px - (px - vp.x) * ratio,
			y: py - (py - vp.y) * ratio,
			zoom: next,
		});
	};
	el.addEventListener("wheel", onWheel, { passive: false });
	return () => el.removeEventListener("wheel", onWheel);
}
