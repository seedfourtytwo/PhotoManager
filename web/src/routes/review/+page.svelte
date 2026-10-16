<script lang="ts">
	import type { AssetOut, HeldItem, Id, ReviewGroup } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { formatShort } from '$lib/dates';
	import { photos } from '$lib/format';
	import { largerOf, reviewOne, reviewTitle, sizeLine } from '$lib/review';
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

	const all = (group: ReviewGroup) => group.items.map((i) => i.asset.id);
	/** The photo's own shape, so nothing is letterboxed; square until its size is known. */
	const ratio = (a: AssetOut) => (a.width && a.height ? a.width / a.height : 1);
</script>

<svelte:head><title>To review · Photos</title></svelte:head>

{#snippet picture(asset: AssetOut, label?: string, larger = false)}
	<figure style:--ratio={ratio(asset)}>
		<div class="frame" style:background={asset.colour ?? undefined}>
			{#if asset.thumb}
				<img src={asset.thumb.url} alt={describePhoto(asset)} loading="lazy" decoding="async" />
			{:else}
				<span class="blank" role="img" aria-label={`${describePhoto(asset)} (preview not ready)`}
				></span>
			{/if}
			{#if label}<span class="label">{label}</span>{/if}
		</div>
		{#if label !== undefined && sizeLine(asset)}
			<figcaption class="small">
				{sizeLine(asset)}{#if larger}<strong class="chip">Larger</strong>{/if}
			</figcaption>
		{/if}
	</figure>
{/snippet}

{#snippet decisions(ids: Id[], one: boolean)}
	<div class="decide">
		<button type="button" class="primary pill" disabled={busy} onclick={() => decide(ids, true)}
			>{one ? 'Keep' : 'Keep all'}</button
		>
		<button type="button" class="pill" disabled={busy} onclick={() => decide(ids, false)}
			>{one ? 'Move to trash' : 'Move all to trash'}</button
		>
	</div>
{/snippet}

<PageHead
	title="To review"
	line={groups?.length ? photos(waiting) : undefined}
	back={{ href: '/collections', label: 'Collections' }}
/>

<div class="page">
	{#if groups && groups.length === 0}
		<div class="empty-state">
			<p>Nothing to review.</p>
			<p>Look-alikes, screenshots and documents found while importing wait here.</p>
		</div>
	{:else if groups}
		<p class="lede">Held back while importing. Keep what you want; the rest goes to the trash.</p>
	{/if}

	{#each groups ?? [] as group (group.reason)}
		{@const one = group.items.length === 1}
		<!-- A group is one card: its name, its photos, and the decision for all of them. -->
		<section class="group" aria-labelledby="r-{group.reason}">
			<header>
				<h2 id="r-{group.reason}">{reviewTitle(group.reason)}</h2>
				<span class="quiet small">{photos(group.items.length)}</span>
			</header>
			{#if group.reason === 'lookalike'}
				<ul class="pairs">
					{#each group.items as item (item.asset.id)}
						{@const larger = item.like ? largerOf(item.asset, item.like) : null}
						<li>
							<!-- scrolls sideways on a phone, so it takes the keyboard too -->
							<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
							<div class="compare" role="group" aria-label="New and in your library" tabindex="0">
								{@render picture(item.asset, 'New', larger === 'first')}
								{#if item.like}{@render picture(
										item.like,
										'In your library',
										larger === 'second'
									)}{/if}
							</div>
							{#if !one}{@render decisions([item.asset.id], true)}{/if}
						</li>
					{/each}
				</ul>
			{:else}
				<ul class="tiles-grid">
					{#each group.items as item (item.asset.id)}
						<li style:--ratio={ratio(item.asset)}>
							<button
								type="button"
								class="tile"
								aria-label={`${describePhoto(item.asset)}: keep or move to trash`}
								onclick={() => (open = { item, reason: group.reason })}
							>
								{@render picture(item.asset)}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
			{@render decisions(all(group), one)}
		</section>
	{/each}
</div>

{#if open}
	{@const { item, reason } = open}
	<Dialog title={reviewOne(reason)} onclose={() => (open = null)}>
		<div class="one">{@render picture(item.asset)}</div>
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
		display: grid;
		gap: var(--s-5);
		padding: 0 var(--page-x) var(--s-7);
	}
	.lede {
		margin: 0;
		color: var(--ink-2);
		line-height: var(--lh-text);
	}
	.group {
		display: grid;
		gap: var(--s-4);
		padding: var(--s-4);
		border-radius: var(--r-2);
		background: var(--raised);
	}
	header {
		display: flex;
		align-items: baseline;
		gap: var(--s-3);
	}
	h2 {
		margin: 0;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	/* Look-alikes: the two photos side by side, each nearly half the card, at its own shape. */
	.pairs {
		display: grid;
		gap: var(--s-6);
	}
	/* Big enough to compare, small enough that the decision stays in view. */
	.pairs li {
		max-width: 64rem;
		display: grid;
		gap: var(--s-3);
	}
	.compare {
		display: flex;
		align-items: flex-end;
		gap: var(--s-3);
	}
	.compare figure {
		flex: var(--ratio) 1 0;
		min-width: 0;
	}
	figure {
		margin: 0;
	}
	.frame {
		position: relative;
		aspect-ratio: var(--ratio);
		overflow: hidden;
		border-radius: var(--r-1);
		background: var(--fill);
	}
	img,
	.blank {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	/* Which is which, on the photo itself. */
	.label {
		position: absolute;
		left: var(--s-2);
		bottom: var(--s-2);
		padding: var(--s-1) var(--s-2);
		border-radius: var(--r-pill);
		background: var(--glass);
		box-shadow: var(--glass-edge);
		backdrop-filter: blur(24px);
		color: var(--ink);
		font-size: var(--fs-13);
		font-weight: 600;
	}
	figcaption {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-2);
		padding-top: var(--s-2);
		color: var(--ink-2);
	}
	.chip {
		padding: 0 var(--s-2);
		border-radius: var(--r-pill);
		background: var(--fill);
		color: var(--ink);
	}
	/* Screenshots, receipts…: a row of photos at their own shapes, no grey bars. */
	.tiles-grid {
		display: flex;
		flex-wrap: wrap;
		gap: var(--fine);
	}
	.tiles-grid li {
		flex: var(--ratio) 1 calc(var(--ratio) * 9rem);
		max-width: calc(var(--ratio) * 18rem);
	}
	.tile {
		display: block;
		width: 100%;
		padding: 0;
		border-radius: var(--r-1);
		transition: scale var(--press) var(--ease);
	}
	.tile:active {
		scale: 0.98;
	}
	.tile .frame {
		border-radius: var(--r-1);
	}
	@media (hover: hover) {
		.tile:hover {
			background: none;
			opacity: 0.9;
		}
	}
	.decide {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-2);
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
		max-width: 24rem;
		margin: 0 auto;
	}
	.one + p {
		margin: var(--s-2) 0 0;
	}
	.empty-state {
		padding-top: 0;
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--s-3) var(--s-7);
		}
		.group {
			padding: var(--s-3);
		}
		/* A phone swipes between the two, each nearly the card's width; the next one peeks in. */
		.compare {
			gap: var(--s-2);
			overflow-x: auto;
			scroll-snap-type: x mandatory;
			scrollbar-width: none;
		}
		.compare figure {
			flex: 0 0 85%;
			scroll-snap-align: center;
		}
		.tiles-grid li {
			flex-basis: calc(var(--ratio) * 6rem);
		}
	}
</style>
