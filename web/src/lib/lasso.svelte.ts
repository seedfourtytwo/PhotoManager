import { idsInRect, selectMany, type Placed, type Rect, type Selection } from './selection';

/**
 * The lasso (desktop): drag across photos with the mouse to select them. The rectangle is
 * kept in screen coordinates for drawing; what it selects is worked out from the photos'
 * places, since most of them are not in the DOM (windowing).
 */

/** A drag shorter than this is still a click. */
const LASSO_SLOP = 8;

export type LassoHost = {
	/** The element the photos are placed in; it captures the pointer while the lasso is out. */
	wrapper: () => HTMLElement | undefined;
	/** The selection as it is: a lasso adds to what was selected when the drag began. */
	selection: () => Selection;
	/** How many photos are loaded. */
	count: () => number;
	/** Another value (by identity) whenever the photos may have moved: a new width, a new row height. */
	layout: () => unknown;
	/** Every loaded photo and its box, in the wrapper's coordinates. */
	placed: () => Placed[];
	onselect: (next: Selection) => void;
};

export function createLasso(host: LassoHost) {
	let start: {
		x: number;
		y: number;
		base: Selection;
		placed: readonly Placed[] | null;
		layout: unknown;
	} | null = null;
	let rect = $state<Rect | null>(null);
	let frame = 0;

	function select() {
		const wrapper = host.wrapper();
		if (!start || !rect || !wrapper) return;
		// From the layout, not the DOM: photos outside the window are not rendered. Every loaded
		// photo's box, in timeline coordinates, is worked out once per drag (again only if a page
		// arrived or the photos moved meanwhile); each frame then only moves the rectangle into
		// those coordinates.
		const layout = host.layout();
		if (start.placed?.length !== host.count() || start.layout !== layout) {
			start.placed = host.placed();
			start.layout = layout;
		}
		const origin = wrapper.getBoundingClientRect();
		const inside = {
			x1: rect.x1 - origin.left,
			y1: rect.y1 - origin.top,
			x2: rect.x2 - origin.left,
			y2: rect.y2 - origin.top
		};
		host.onselect(selectMany(start.base, idsInRect(start.placed, inside), true));
	}

	return {
		/** The rectangle being dragged, in screen coordinates; null when no lasso is out. */
		get rect(): Rect | null {
			return rect;
		},

		down(event: PointerEvent) {
			if (event.pointerType !== 'mouse' || event.button !== 0) return;
			start = {
				x: event.clientX,
				y: event.clientY + window.scrollY,
				base: host.selection(),
				placed: null,
				layout: null
			};
		},

		move(event: PointerEvent) {
			const wrapper = host.wrapper();
			if (!start || !wrapper) return;
			const next = {
				x1: start.x,
				y1: start.y - window.scrollY,
				x2: event.clientX,
				y2: event.clientY
			};
			if (!rect && Math.hypot(next.x2 - next.x1, next.y2 - next.y1) < LASSO_SLOP) return;
			if (!rect) wrapper.setPointerCapture(event.pointerId);
			rect = next;
			// Many pointer events per frame: select once per frame.
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(select);
		},

		/** The button came up (a click follows), or the browser took the pointer away. */
		end(clickFollows: boolean) {
			cancelAnimationFrame(frame);
			if (rect) {
				select(); // where the drag ended, even if its frame had not come yet
				if (clickFollows) {
					// The click that ends a lasso must not open or toggle the photo under the pointer.
					// It comes right after the pointerup, if at all: disarm so no later click is lost.
					const swallow = (e: Event) => e.stopPropagation();
					window.addEventListener('click', swallow, { capture: true, once: true });
					setTimeout(() => window.removeEventListener('click', swallow, { capture: true }));
				}
			}
			start = null;
			rect = null;
		}
	};
}
