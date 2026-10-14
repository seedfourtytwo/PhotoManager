/**
 * A bottom sheet follows the finger down from its handle or title and closes when let go far
 * enough or fast enough; otherwise it springs back (DESIGN_PRINCIPLES §2, Dialogs).
 */

/** px pulled down that close the sheet whatever the speed. */
export const CLOSE_DISTANCE = 96;
/** px per ms: a flick this fast closes it from a short pull. */
export const CLOSE_SPEED = 0.6;
/** A flick still needs this many px, so a tap that jitters does not close. */
const FLICK_MIN = 24;

export function shouldClose(pulled: number, ms: number): boolean {
	if (pulled >= CLOSE_DISTANCE) return true;
	return pulled >= FLICK_MIN && ms > 0 && pulled / ms >= CLOSE_SPEED;
}

/** Svelte action: drag `node` down by its `[data-grab]` or `h2` on a phone-sized screen. */
export function sheetDrag(node: HTMLElement, onclose: () => void) {
	let start: { y: number; t: number; id: number } | null = null;
	let pulled = 0;
	const phone = () => matchMedia('(max-width: 639px)').matches;

	function down(e: PointerEvent) {
		if (!phone() || !(e.target as Element).closest('[data-grab], h2')) return;
		start = { y: e.clientY, t: e.timeStamp, id: e.pointerId };
		pulled = 0;
		node.setPointerCapture(e.pointerId);
		node.style.transition = 'none';
	}
	function move(e: PointerEvent) {
		if (!start || e.pointerId !== start.id) return;
		pulled = Math.max(0, e.clientY - start.y);
		node.style.translate = `0 ${pulled}px`;
	}
	function up(e: PointerEvent) {
		if (!start || e.pointerId !== start.id) return;
		const close = shouldClose(pulled, e.timeStamp - start.t);
		start = null;
		node.style.transition = '';
		node.style.translate = close ? '0 100%' : '';
		if (close) onclose();
	}
	node.addEventListener('pointerdown', down);
	node.addEventListener('pointermove', move);
	node.addEventListener('pointerup', up);
	node.addEventListener('pointercancel', up);
	return {
		update(next: () => void) {
			onclose = next;
		},
		destroy() {
			node.removeEventListener('pointerdown', down);
			node.removeEventListener('pointermove', move);
			node.removeEventListener('pointerup', up);
			node.removeEventListener('pointercancel', up);
		}
	};
}
