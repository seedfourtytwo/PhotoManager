<script lang="ts" generics="T extends string">
	import { flip } from 'svelte/animate';
	import IconButton from './IconButton.svelte';

	/**
	 * Some of a list, each with a switch, in an order of one's own (Collections rows, Home
	 * sections): the ones shown first in their order, each but the first with Move up, then
	 * the others switched off. The last one shown cannot be switched off.
	 */
	type Props = {
		label: string;
		all: readonly T[];
		/** The ones shown, in their order. */
		chosen: readonly T[];
		names: Record<T, string>;
		onchange: (chosen: T[]) => void;
	};
	let { label, all, chosen, names, onchange }: Props = $props();
	const id = $props.id();
	const rows = $derived([...new Set([...chosen, ...all])]);
	// a row moves to its new place (transform only); a reader who asked for less motion jumps
	const moving =
		typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
			? 0
			: 240;

	function toggle(item: T, on: boolean) {
		const kept = chosen.filter((c) => c !== item);
		onchange(on ? [...kept, item] : kept);
	}

	function moveUp(item: T) {
		const order = [...chosen];
		const at = order.indexOf(item);
		[order[at - 1], order[at]] = [order[at], order[at - 1]];
		onchange(order);
	}
</script>

<div role="group" aria-labelledby={id}>
	<div class="group-label"><h3 {id}>{label}</h3></div>
	<ul class="tiles">
		{#each rows as item (item)}
			{@const at = chosen.indexOf(item)}
			<li class="tile-row" animate:flip={{ duration: moving }}>
				<span class="tile-main"><span class="tile-title">{names[item]}</span></span>
				{#if at > 0}
					<IconButton icon="up" label={`Move ${names[item]} up`} onclick={() => moveUp(item)} />
				{/if}
				<input
					type="checkbox"
					role="switch"
					aria-label={names[item]}
					checked={at >= 0}
					disabled={at >= 0 && chosen.length === 1}
					onchange={(e) => toggle(item, e.currentTarget.checked)}
				/>
			</li>
		{/each}
	</ul>
</div>
