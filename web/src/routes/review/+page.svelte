<script lang="ts">
	import type { AssetOut, HeldItem, Id, ReviewGroup } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { formatShort } from '$lib/dates';
	import { photos } from '$lib/format';
	import { reviewOne, reviewTitle } from '$lib/review';
	import Dialog from '$lib/components/Dialog.svelte';
	import PageHead from '$lib/components/PageHead.svelte';
	import { describePhoto } from '$lib/components/PhotoGrid.svelte';

	let groups = $state.raw<ReviewGroup[] | null>(null);
	let busy = $state(false); // one decision at a time: a double click must not act twice
	/** One photo opened to decide on its own, with the reason it waits. */
	let open = $state<{ item: HeldItem; reason: string } | null>(null);

	const waiting = $derived(groups?.reduce((n, g) => n + g.items.length, 0) ?? 0);

	async function load() {
		try {
			groups = (await api.review()).groups;
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => void load());

	async function decide(ids: Id[], keep: boolean) {
		if (busy) return;
		busy = true;
		try {
			if (keep) {
				const { kept } = await api.keepHeld(ids);
				notice.show(`Kept ${photos(kept)}: now in your library.`);
			} else {
				const { discarded } = await api.discardHeld(ids);
				notice.show(`Moved ${photos(discarded)} to the trash.`);
			}
			open = null;
			library.changed();
			await load();
		} catch (e) {
			notice.error(e);
			await load(); // someone else may have decided in the meantime
		} finally {
			busy = false;
		}
	}

	const size = (a: AssetOut) => (a.width && a.height ? `${a.width} × ${a.height}` : '');
	const all = (group: ReviewGroup) => group.items.map((i) => i.asset.id);
</script>

<svelte:head><title>To review · Photos</title></svelte:head>

{#snippet picture(asset: AssetOut, caption?: string)}
	<figure>
		{#if asset.thumb}
			<img src={asset.thumb.url} alt={describePhoto(asset)} loading="lazy" decoding="async" />
		{:else}
			<span class="blank" role="img" aria-label={`${describePhoto(asset)} (preview not ready)`}
			></span>
		{/if}
		{#if caption !== undefined}
			<figcaption class="small">
				<strong>{caption}</strong>
				<span class="quiet data">{size(asset)}</span>
			</figcaption>
		{/if}
	</figure>
{/snippet}

<PageHead
	title="To review"
	line={groups?.length ? photos(waiting) : undefined}
	back={{ href: '/collections', label: 'Collections' }}
/>

<div class="page">
	<p class="lede">
		These were copied in but held back. Keep what you want in your library; the rest goes to the
		trash.
	</p>

	{#if groups && groups.length === 0}
		<div class="empty-state">
			<p>Nothing to review.</p>
			<p>Look-alikes, screenshots and documents found during an import will wait here.</p>
		</div>
	{/if}

	{#each groups ?? [] as group (group.reason)}
		{@const one = group.items.length === 1}
		<section aria-labelledby="r-{group.reason}">
			<h2 id="r-{group.reason}">{reviewTitle(group.reason)}</h2>
			<ul class:pairs={group.reason === 'lookalike'}>
				{#each group.items as item (item.asset.id)}
					<li>
						<button
							type="button"
							class="tile"
							aria-label={`${describePhoto(item.asset)}: keep or move to trash`}
							onclick={() => (open = { item, reason: group.reason })}
						>
							{@render picture(item.asset, item.like ? 'New' : undefined)}
							{#if item.like}{@render picture(item.like, 'In your library')}{/if}
						</button>
					</li>
				{/each}
			</ul>
			<!-- One decision for the whole group; a photo on its own opens from its tile. -->
			<div class="decide">
				<button
					type="button"
					class="primary pill"
					disabled={busy}
					onclick={() => decide(all(group), true)}>{one ? 'Keep' : 'Keep all'}</button
				>
				<button type="button" class="pill" disabled={busy} onclick={() => decide(all(group), false)}
					>{one ? 'Move to trash' : 'Move all to trash'}</button
				>
			</div>
		</section>
	{/each}
</div>

{#if open}
	{@const { item, reason } = open}
	<Dialog title={reviewOne(reason)} onclose={() => (open = null)}>
		<div class="one" class:pair={!!item.like}>
			{@render picture(item.asset, item.like ? 'New' : '')}
			{#if item.like}{@render picture(item.like, 'In your library')}{/if}
		</div>
		<p class="quiet small">{formatShort(item.asset.taken_at)}</p>
		{#snippet actions()}
			<button type="button" disabled={busy} onclick={() => decide([item.asset.id], false)}
				>Move to trash</button
			>
			<button
				type="button"
				class="primary"
				disabled={busy}
				onclick={() => decide([item.asset.id], true)}>Keep</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	.lede {
		max-width: var(--measure);
		margin: 0 0 var(--s-5);
		color: var(--ink-2);
		line-height: var(--lh-text);
	}
	section + section {
		margin-top: var(--s-7);
	}
	h2 {
		margin: 0 0 var(--s-3);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
		gap: var(--fine);
	}
	ul.pairs {
		grid-template-columns: repeat(auto-fill, minmax(20rem, 1fr));
		gap: var(--s-3);
	}
	/* A tile is the photo (or the pair) itself: a press opens it to decide on its own. */
	.tile {
		display: flex;
		gap: var(--fine);
		width: 100%;
		padding: 0;
		border-radius: 0;
		text-align: left;
		transition: transform var(--press) var(--ease);
	}
	.tile:active {
		transform: scale(0.98);
	}
	@media (hover: hover) {
		.tile:hover {
			background: none;
			opacity: 0.9;
		}
	}
	figure {
		flex: 1;
		min-width: 0;
		margin: 0;
	}
	img,
	.blank {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 3;
		object-fit: contain;
		background: var(--hairline);
	}
	figcaption {
		display: flex;
		flex-wrap: wrap;
		gap: 0 var(--s-2);
		padding: var(--s-1) var(--s-1) 0;
	}
	.decide {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
		margin-top: var(--s-3);
	}
	.pill {
		min-height: var(--target);
		padding: 0 var(--s-5);
		border-radius: var(--r-pill);
		background: var(--fill);
		font-weight: 600;
	}
	.pill.primary {
		background: var(--ink);
		color: var(--bg);
	}
	.one {
		display: flex;
		gap: var(--fine);
	}
	.one + p {
		margin: var(--s-2) 0 0;
	}
	.empty-state {
		padding-top: 0;
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		.lede,
		h2,
		.decide,
		.empty-state {
			padding-inline: var(--s-2);
		}
		ul.pairs {
			grid-template-columns: 1fr;
		}
	}
</style>
