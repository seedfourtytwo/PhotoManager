<script lang="ts" module>
	import type { AssetOut, Id } from '$lib/api';
	import { formatShort } from '$lib/dates';

	export function describePhoto(item: AssetOut): string {
		const where = item.place?.city ?? item.place?.country;
		return `Photo, ${formatShort(item.taken_at)}${where ? `, ${where}` : ''}${item.favourite ? ', favourite' : ''}`;
	}
</script>

<script lang="ts">
	import { tick } from 'svelte';
	import { NAV_KEYS, neighbour, type Layout, type NavKey } from '$lib/timeline';

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
			navigator.vibrate?.(10);
			ontoggle(id, false);
		}, LONG_PRESS_MS);
	}

	function onpointermove(event: PointerEvent) {
		if (!pressStart) return;
		if (Math.hypot(event.clientX - pressStart.x, event.clientY - pressStart.y) > 10) cancelPress();
	}

	function cancelPress() {
		clearTimeout(pressTimer);
		pressStart = null;
		if (pressFired) longPressAt = performance.now();
		pressFired = false;
	}

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
				onpointerup={cancelPress}
				onpointercancel={cancelPress}
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
				{#if item.thumb}
					<img src={item.thumb.url} alt={describePhoto(item)} loading="lazy" decoding="async" />
				{:else}
					<span class="visually-hidden">{describePhoto(item)} (preview not ready)</span>
				{/if}
				{#if item.favourite}<span class="fav" aria-hidden="true">♥</span>{/if}
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
		background: var(--hairline);
		overflow: hidden;
		-webkit-touch-callout: none;
		user-select: none;
	}
	.tile:focus-visible {
		outline-offset: -2px;
		z-index: 1;
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: fill; /* the box already has the photo's true aspect ratio */
		pointer-events: none;
	}
	/* Selection: the accent, as an inset frame; the photo stays uncropped. */
	.tile.selected::after {
		content: '';
		position: absolute;
		inset: 0;
		box-shadow: inset 0 0 0 3px var(--accent);
	}
	.check {
		position: absolute;
		top: 6px;
		left: 6px;
		width: 18px;
		height: 18px;
		border-radius: 50%;
		box-sizing: border-box;
		border: 1.5px solid rgb(255 255 255 / 0.9);
		background: rgb(0 0 0 / 0.15);
		opacity: 0;
		transition: opacity var(--motion);
	}
	/* The circle appears where it helps — under the mouse or keyboard focus — and stays on
	   selected photos; unselected photos stay clean while selecting. */
	@media (hover: hover) {
		.tile:hover .check {
			opacity: 1;
		}
	}
	.tile:focus-visible .check {
		opacity: 1;
	}
	.tile.selected .check {
		background: var(--accent);
		border-color: var(--accent);
		opacity: 1;
	}
	.fav {
		position: absolute;
		right: 5px;
		bottom: 2px;
		color: #fff;
		font-size: 12px;
		text-shadow: 0 0 2px rgb(0 0 0 / 0.6);
	}
	@media (hover: none) {
		.check {
			width: 22px;
			height: 22px;
		}
	}
</style>
