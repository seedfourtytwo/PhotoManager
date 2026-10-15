/**
 * A bottom sheet follows the finger down from its handle or title and closes when let go far
 * enough or fast enough; otherwise it springs back from the speed it was let go at
 * (DESIGN_PRINCIPLES §1.9, §2 Dialogs).
 */
import { velocity } from './gesture';
import { animate } from './spring';

/** px pulled down that close the sheet whatever the speed. */
export const CLOSE_DISTANCE = 96;
/** px per ms at release: a flick this fast closes it from a short pull. */
export const CLOSE_SPEED = 0.6;
/** A flick still needs this many px, so a tap that jitters does not close. */
const FLICK_MIN = 24;

/** `speed`: the finger's downward speed as it let go, px/ms (negative going back up). */
export function shouldClose(pulled: number, speed: number): boolean {
	if (pulled >= CLOSE_DISTANCE) return true;
	return pulled >= FLICK_MIN && speed >= CLOSE_SPEED;
}

/** The finger's downward speed over its last moves, px/ms; 0 when that says nothing. */
export function releaseSpeed(samples: { y: number; t: number }[]): number {
	return velocity(samples.map(({ y, t }) => ({ x: y, y: 0, t })));
}

/** Svelte action: drag `node` down by its `[data-grab]` or `h2` on a phone-sized screen. */
export function sheetDrag(node: HTMLElement, onclose: () => void) {
	let start: { y: number; id: number; from: number } | null = null;
	let samples: { y: number; t: number }[] = [];
	let pulled = 0;
	let back: { stop(): number } | null = null;
	const phone = () => matchMedia('(max-width: 639px)').matches;

	function down(e: PointerEvent) {
		if (!phone() || !(e.target as Element).closest('[data-grab], h2')) return;
		// A finger that lands while the sheet springs back catches it where it is.
		const from = back?.stop() ?? 0;
		back = null;
		start = { y: e.clientY, id: e.pointerId, from };
		samples = [{ y: e.clientY, t: e.timeStamp }];
		pulled = from;
		node.setPointerCapture(e.pointerId);
		node.style.transition = 'none';
	}
	function move(e: PointerEvent) {
		if (!start || e.pointerId !== start.id) return;
		samples.push({ y: e.clientY, t: e.timeStamp });
		pulled = Math.max(0, start.from + e.clientY - start.y);
		node.style.translate = `0 ${pulled}px`;
	}
	function up(e: PointerEvent) {
		if (!start || e.pointerId !== start.id) return;
		const speed = releaseSpeed(samples);
		start = null;
		if (e.type === 'pointerup' && shouldClose(pulled, speed)) {
			node.style.transition = '';
			node.style.translate = '0 100%';
			onclose();
			return;
		}
		back = animate({
			from: pulled,
			to: 0,
			velocity: speed,
			onFrame: (y) => (node.style.translate = `0 ${y}px`),
			onRest: () => {
				back = null;
				node.style.translate = '';
				node.style.transition = '';
			}
		});
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
			back?.stop();
			node.removeEventListener('pointerdown', down);
			node.removeEventListener('pointermove', move);
			node.removeEventListener('pointerup', up);
			node.removeEventListener('pointercancel', up);
		}
	};
}
