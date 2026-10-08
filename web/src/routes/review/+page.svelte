<script lang="ts">
	import type { AssetOut, Id, ReviewGroup } from '$lib/api';
	import { api, library, notice } from '$lib/app.svelte';
	import { formatShort } from '$lib/dates';
	import { photos, reviewTitle } from '$lib/review';
	import { describePhoto } from '$lib/components/PhotoGrid.svelte';

	let groups = $state.raw<ReviewGroup[] | null>(null);
	let busy = $state(false); // one decision at a time: a double click must not act twice

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

{#snippet picture(asset: AssetOut, caption: string)}
	<figure>
		{#if asset.thumb}
			<img src={asset.thumb.url} alt={describePhoto(asset)} loading="lazy" decoding="async" />
		{:else}
			<span class="blank quiet small">preview not ready</span>
		{/if}
		<figcaption class="small">
			{#if caption}<strong>{caption}</strong>{/if}
			<span class="quiet"
				>{formatShort(asset.taken_at)}{size(asset) ? ` · ${size(asset)}` : ''}</span
			>
		</figcaption>
	</figure>
{/snippet}

<div class="page">
	<header>
		<h1>To review</h1>
		<p class="prose">
			These photos were copied in but kept out of your library until you decide. Keep adds a photo
			to the library. Discard moves it to the trash, where it stays 30 days. Your folders and cloud
			drives are never touched.
		</p>
	</header>

	{#if groups && groups.length === 0}
		<div class="empty-state">
			<p>Nothing to review.</p>
			<p>Look-alikes, screenshots and documents found during an import will wait here.</p>
		</div>
	{/if}

	{#each groups ?? [] as group (group.reason)}
		<section aria-labelledby="r-{group.reason}">
			<div class="head">
				<h2 id="r-{group.reason}">
					{reviewTitle(group.reason)} <span class="quiet">{group.items.length}</span>
				</h2>
				<div class="tools">
					<button type="button" disabled={busy} onclick={() => decide(all(group), true)}
						>Keep all</button
					>
					<button type="button" disabled={busy} onclick={() => decide(all(group), false)}
						>Discard all</button
					>
				</div>
			</div>
			<ul class:pairs={group.reason === 'lookalike'}>
				{#each group.items as item (item.asset.id)}
					<li>
						<div class="pictures">
							{@render picture(item.asset, item.like ? 'New' : '')}
							{#if item.like}{@render picture(item.like, 'In your library')}{/if}
						</div>
						<div class="tools">
							<button type="button" disabled={busy} onclick={() => decide([item.asset.id], true)}
								>Keep</button
							>
							<button type="button" disabled={busy} onclick={() => decide([item.asset.id], false)}
								>Discard</button
							>
						</div>
					</li>
				{/each}
			</ul>
		</section>
	{/each}
</div>

<style>
	.page {
		padding: 0 var(--page-x) var(--s-7);
	}
	header {
		padding: var(--s-5) 0 var(--s-4);
	}
	header p {
		margin: var(--s-3) 0 0;
	}
	section {
		padding: var(--s-4) 0;
		border-top: 1px solid var(--hairline);
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: var(--s-2);
		margin-bottom: var(--s-3);
	}
	h2 {
		margin: 0;
	}
	.tools {
		display: flex;
		gap: 0 2px;
		margin-left: calc(-1 * var(--s-2));
	}
	.tools button {
		color: var(--ink-2);
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
		gap: var(--s-4) var(--s-3);
	}
	ul.pairs {
		grid-template-columns: repeat(auto-fill, minmax(22rem, 1fr));
	}
	.pictures {
		display: flex;
		gap: var(--s-2);
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
	.blank {
		display: grid;
		place-items: center;
	}
	figcaption {
		display: flex;
		flex-direction: column;
		padding-top: var(--s-1);
	}
	.empty-state {
		padding-top: var(--s-4);
	}
	@media (max-width: 639px) {
		.page {
			padding: 0 var(--gutter) var(--s-7);
		}
		header,
		section,
		.empty-state {
			padding-inline: var(--s-2);
		}
		ul.pairs {
			grid-template-columns: 1fr;
		}
	}
</style>
