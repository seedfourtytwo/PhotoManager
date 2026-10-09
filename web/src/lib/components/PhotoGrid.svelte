<script lang="ts" module>
	import type { AssetOut, Id } from '$lib/api';
	import { formatShort } from '$lib/dates';

	export function describePhoto(item: AssetOut): string {
		const where = item.place?.city ?? item.place?.country;
		return `Photo, ${formatShort(item.taken_at)}${where ? `, ${where}` : ''}${item.favourite ? ', favourite' : ''}`;
	}
</script>

<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { SvelteMap } from 'svelte/reactivity';
	import { NAV_KEYS, letterboxed, neighbour, type Layout, type NavKey } from '$lib/timeline';

	type Props = {
		items: AssetOut[];
		layout: Layout;
		selected: ReadonlySet<Id>;
		/** When something is selected, a tap/click toggles instead of opening. */
		selecting: boolean;
		onopen: (id: Id) => void;
		ontoggle: (id: Id, range: boolean) => void;
		/** Album arrange mode: drag or Alt+←/→ to move a photo. */
		arrange?: boolean;
		onmove?: (id: Id, to: number) => void;
		/** Only render items [start, end) (windowing); the grid keeps its full height. */
		range?: [number, number];
		/**
		 * Roving tab stop: the one tile reachable with Tab (null: none in this grid). Left
		 * undefined, the grid manages it itself (first tile, then the last one focused).
		 */
		active?: Id | null;
		onfocusphoto?: (id: Id) => void;
		/** Arrow keys: handled by the caller (a timeline spanning several grids) when given. */
		onnav?: (id: Id, key: NavKey) => void;
		/** Accessible name of the grid. */
		label?: string;
	};
	let {
		items,
		layout,
		selected,
		selecting,
		onopen,
		ontoggle,
		arrange = false,
		onmove,
		range,
		active,
		onfocusphoto,
		onnav,
		label = 'Photos'
	}: Props = $props();

	let own = $state<Id | null>(null);
	const tabStop = $derived(
		active !== undefined
			? active
			: own !== null && items.some((a) => a.id === own)
				? own
				: (items[0]?.id ?? null)
	);
	/** Rendered tiles: the window, plus the tab stop so focus never falls off the page. */
	const shown = $derived.by(() => {
		const [start, end] = range ?? [0, items.length];
		const out: { item: AssetOut; i: number }[] = [];
		for (let i = start; i < Math.min(end, items.length); i++) out.push({ item: items[i], i });
		const stop = tabStop === null ? -1 : items.findIndex((a) => a.id === tabStop);
		if (stop >= 0 && (stop < start || stop >= end)) {
			out.push({ item: items[stop], i: stop });
			out.sort((a, b) => a.i - b.i);
		}
		return out;
	});
	let grid: HTMLElement | undefined = $state();
	/**
	 * Photos whose thumbnail did not load: their tiles stay plain instead of broken. Kept as
	 * the very item that failed, so the same photo loaded anew (a reload) is tried again.
	 */
	const failed = new SvelteMap<Id, AssetOut>();

	async function focusTile(id: Id) {
		own = id;
		await tick();
		grid?.querySelector<HTMLElement>(`.tile[data-id="${id}"]`)?.focus();
	}

	const LONG_PRESS_MS = 450;
	let pressTimer: ReturnType<typeof setTimeout> | undefined;
	let pressStart: { x: number; y: number } | null = null;
	// A long press already toggled; the click some browsers send right after must not undo it.
	let longPressAt = -Infinity;
	let longPressId: Id | null = null;
	let pressFired = false;
	/** After a long press: the photo the finger was last over, so each one is taken once. */
	let pressOver: Id | null = null;
	let dragged: Id | null = null;

	function onclick(event: MouseEvent, id: Id) {
		if (id === longPressId && performance.now() - longPressAt < 500) return;
		const onCheck = (event.target as HTMLElement).closest('.check');
		if (onCheck || selecting || event.shiftKey || event.metaKey || event.ctrlKey)
			ontoggle(id, event.shiftKey);
		else onopen(id);
	}

	function onpointerdown(event: PointerEvent, id: Id) {
		if (event.pointerType !== 'touch' || arrange) return;
		pressStart = { x: event.clientX, y: event.clientY };
		clearTimeout(pressTimer);
		pressTimer = setTimeout(() => {
			pressFired = true;
			longPressId = id;
			pressOver = id;
			navigator.vibrate?.(10);
			ontoggle(id, false);
		}, LONG_PRESS_MS);
	}

	function onpointermove(event: PointerEvent) {
		if (!pressStart) return;
		if (pressFired) dragSelect(event);
		else if (Math.hypot(event.clientX - pressStart.x, event.clientY - pressStart.y) > 10)
			cancelPress();
	}

	/** Long-press then drag: the run from the pressed photo to the one now under the finger. */
	function dragSelect(event: PointerEvent) {
		// A touch stays captured by the tile it went down on, so the tile is looked up by place;
		// it may belong to another month's grid.
		const tile = document
			.elementFromPoint(event.clientX, event.clientY)
			?.closest<HTMLElement>('.tile[data-id]');
		const id = tile ? Number(tile.dataset.id) : null;
		if (id === null || id === pressOver) return;
		pressOver = id;
		ontoggle(id, true);
	}

	// Only a touchmove listener that is not passive can keep the page from scrolling under a
	// finger, and it has to be there before the touch starts. It lets everything scroll until
	// a long press has fired.
	$effect(() => {
		const element = grid;
		if (!element) return;
		const hold = (event: TouchEvent) => {
			if (pressFired && event.cancelable) event.preventDefault();
		};
		element.addEventListener('touchmove', hold, { passive: false });
		return () => element.removeEventListener('touchmove', hold);
	});

	// Heard on the window, not on the tile: the windowed grid may take the pressed tile off the
	// page before the finger lifts, and the press has to end all the same.
	function cancelPress() {
		clearTimeout(pressTimer);
		pressStart = null;
		if (pressFired) longPressAt = performance.now();
		pressFired = false;
	}
	onDestroy(() => clearTimeout(pressTimer));

	function onkeydown(event: KeyboardEvent, id: Id, index: number) {
		const plain = !event.altKey && !event.metaKey && !event.ctrlKey && !event.shiftKey;
		if (plain && NAV_KEYS.includes(event.key)) {
			event.preventDefault();
			const key = event.key as NavKey;
			if (onnav) onnav(id, key);
			else {
				const to = neighbour(layout.boxes, index, key);
				if (to !== null) void focusTile(items[to].id);
			}
			return;
		}
		if (event.key === 'x' || (event.key === ' ' && selecting)) {
			event.preventDefault();
			ontoggle(id, event.shiftKey);
		} else if (
			arrange &&
			event.altKey &&
			(event.key === 'ArrowLeft' || event.key === 'ArrowRight')
		) {
			event.preventDefault();
			const to = index + (event.key === 'ArrowLeft' ? -1 : 1);
			if (to >= 0 && to < items.length) onmove?.(id, to);
		}
	}

	function ondrop(event: DragEvent, index: number) {
		event.preventDefault();
		if (dragged === null) return;
		const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
		const after = event.clientX > rect.left + rect.width / 2;
		const from = items.findIndex((a) => a.id === dragged);
		let to = index + (after ? 1 : 0);
		if (from < to) to--;
		if (to !== from) onmove?.(dragged, to);
		dragged = null;
	}
</script>

<svelte:window onpointerup={cancelPress} onpointercancel={cancelPress} />

<div
	class="grid"
	role="group"
	aria-label={label}
	bind:this={grid}
	style:height={`${layout.height}px`}
>
	{#each shown as { item, i } (item.id)}
		{@const box = layout.boxes[i]}
		{#if box}
			<button
				type="button"
				class="tile"
				class:selected={selected.has(item.id)}
				data-id={item.id}
				tabindex={item.id === tabStop ? 0 : -1}
				onfocus={() => {
					own = item.id;
					onfocusphoto?.(item.id);
				}}
				aria-pressed={selecting || selected.has(item.id) ? selected.has(item.id) : undefined}
				style:transform={`translate(${box.x}px, ${box.y}px)`}
				style:width={`${box.w}px`}
				style:height={`${box.h}px`}
				draggable={arrange}
				onclick={(e) => onclick(e, item.id)}
				onpointerdown={(e) => onpointerdown(e, item.id)}
				{onpointermove}
				oncontextmenu={(e) => {
					if (pressStart) e.preventDefault();
				}}
				onkeydown={(e) => onkeydown(e, item.id, i)}
				ondragstart={(e) => {
					dragged = item.id;
					e.dataTransfer?.setData('text/plain', String(item.id));
				}}
				ondragover={(e) => arrange && e.preventDefault()}
				ondrop={(e) => ondrop(e, i)}
			>
				{#if item.thumb && failed.get(item.id) !== item}
					<img
						class:whole={letterboxed(item)}
						src={item.thumb.url}
						alt={describePhoto(item)}
						loading="lazy"
						decoding="async"
						onerror={() => failed.set(item.id, item)}
					/>
				{:else if item.thumb}
					<span class="visually-hidden">{describePhoto(item)} (preview missing)</span>
				{:else}
					<span class="visually-hidden">{describePhoto(item)} (preview not ready)</span>
				{/if}
				{#if item.favourite}<svg class="fav" viewBox="0 0 16 16" aria-hidden="true"
						><path
							d="M8 13.6S2.2 10.1 2.2 6.1A2.9 2.9 0 0 1 8 4.9a2.9 2.9 0 0 1 5.8 1.2c0 4-5.8 7.5-5.8 7.5z"
						/></svg
					>{/if}
				<span class="check" aria-hidden="true"></span>
			</button>
		{/if}
	{/each}
</div>

<style>
	.grid {
		position: relative;
		contain: layout;
	}
	.tile {
		position: absolute;
		left: 0;
		top: 0;
		padding: 0;
		min-height: 0;
		border-radius: 0;
		background: var(--hairline);
		overflow: hidden;
		-webkit-touch-callout: none;
		user-select: none;
		transition: none;
	}
	@media (hover: hover) {
		.tile:hover {
			background: var(--hairline);
		}
	}
	.tile:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
		border-radius: 0;
		z-index: 1;
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: fill; /* the box already has the photo's true aspect ratio */
		pointer-events: none;
	}
	/* A panorama or a tall strip gets a tile of a sane shape, and sits whole inside it. */
	img.whole {
		object-fit: contain;
	}
	/* Selection: the accent as an inset frame (a hairline of shade keeps it visible on any
	   photo); the photo itself stays uncropped and undimmed. */
	.tile.selected::after {
		content: '';
		position: absolute;
		inset: 0;
		box-shadow:
			inset 0 0 0 3px var(--accent),
			inset 0 0 0 4px rgb(0 0 0 / 0.25);
	}
	.check {
		position: absolute;
		top: var(--s-2);
		left: var(--s-2);
		width: 20px;
		height: 20px;
		border-radius: 50%;
		box-sizing: border-box;
		border: 1.5px solid #fff;
		background: rgb(0 0 0 / 0.18) center / 14px no-repeat;
		box-shadow: 0 0 0 1px rgb(0 0 0 / 0.2);
		opacity: 0;
		transition: opacity var(--motion) var(--ease);
	}
	/* The circle appears where it helps — under the mouse or keyboard focus — and stays on
	   selected photos; unselected photos stay clean while selecting. */
	@media (hover: hover) {
		@media (hover: hover) {
			.tile:hover .check {
				opacity: 1;
			}
		}
	}
	.tile:focus-visible .check {
		opacity: 1;
	}
	.tile.selected .check {
		background-color: var(--accent);
		background-image: var(--check);
		border-color: var(--accent);
		opacity: 1;
	}
	.fav {
		position: absolute;
		right: var(--s-1);
		bottom: var(--s-1);
		width: 14px;
		height: 14px;
		fill: #fff;
		filter: drop-shadow(0 0 1.5px rgb(0 0 0 / 0.55));
	}
	@media (hover: none) {
		.check {
			width: 24px;
			height: 24px;
			background-size: 16px;
		}
	}
</style>
