<script lang="ts">
	import { page } from '$app/state';
	import {
		ApiError,
		type AlbumDetail,
		type AssetOut,
		type PrintOptions,
		type PrintPlan,
		type PrintRequest
	} from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatShort } from '$lib/dates';
	import { errorMessage, photos } from '$lib/format';

	/** Previews are small multiples: identical, low-resolution pages side by side. */
	const PREVIEW_PPI = 40;

	const id = $derived(Number(page.params.id));
	let album = $state<AlbumDetail | null>(null);
	let options = $state<PrintOptions | null>(null);
	let plan = $state<PrintPlan | null>(null);
	let error = $state('');
	let printError = $state('');
	let trim = $state('a4-landscape');
	let theme = $state('quiet');
	let cover = $state(true);
	let cropMarks = $state(false);
	let anyway = $state(false);
	let busy = $state(false);

	const request = $derived<PrintRequest>({ trim, theme, cover, crop_marks: cropMarks });
	const byId = $derived(new Map((album?.items ?? []).map((a) => [a.id, a])));
	const blocking = $derived(plan?.issues.filter((i) => i.level === 'block') ?? []);
	const pages = $derived(Array.from({ length: plan?.page_count ?? 0 }, (_, i) => i + 1));
	const trimLabel = $derived(options?.trims.find((t) => t.id === trim)?.label ?? trim);

	$effect(() => {
		const albumId = id;
		Promise.all([api.album(albumId), api.printOptions()])
			.then(([a, o]) => {
				album = a;
				options = o;
			})
			.catch((e: unknown) => (error = errorMessage(e, 'Could not open the album.')));
	});

	// The plan (pages and resolution issues) follows every choice; nothing is rendered for it.
	$effect(() => {
		const body = request;
		const albumId = id;
		let stale = false;
		printError = '';
		api
			.printPlan(albumId, body)
			.then((p) => !stale && (plan = p))
			.catch((e: unknown) => {
				if (stale) return;
				// Not the whole-page error: the form stays, so another choice can fix it.
				plan = null;
				printError = errorMessage(e, 'Could not plan the pages.');
			});
		return () => (stale = true);
	});

	function pageLabel(n: number): string {
		if (cover && n === 1) return 'Cover';
		return `Page ${n}`;
	}

	function describe(asset: AssetOut | undefined): string {
		return asset ? formatShort(asset.taken_at) : 'a photo';
	}

	async function download() {
		if (busy) return;
		busy = true;
		printError = '';
		try {
			const pdf = await api.printPdf(id, { ...request, allow_low_resolution: anyway });
			const url = URL.createObjectURL(pdf.blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = pdf.filename;
			document.body.append(a);
			a.click();
			a.remove();
			setTimeout(() => URL.revokeObjectURL(url), 60_000);
			notice.show(
				`Saved ${pdf.filename}${pdf.warnings ? ` (${photos(pdf.warnings)} may look soft)` : ''}.`
			);
		} catch (e) {
			printError =
				e instanceof ApiError && e.status === 422 && blocking.length
					? `${e.message}. Choose a smaller size, take those photos out, or tick “Print anyway”.`
					: errorMessage(e, 'Could not make the PDF.');
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Print {album?.title ?? 'album'} · Photos</title></svelte:head>

<div class="page">
	<p class="small crumb"><a href={`/albums/${id}`}>{album?.title ?? 'Album'}</a></p>
	<h1>Print {album ? `“${album.title}”` : ''}</h1>

	{#if error}
		<p role="alert">{error}</p>
	{:else}
		<div class="layout">
			<form class="choices" onsubmit={(e) => e.preventDefault()}>
				<label class="field">
					Size
					<select bind:value={trim}>
						{#each options?.trims ?? [] as t (t.id)}
							<option value={t.id}>{t.label}</option>
						{/each}
					</select>
				</label>
				<fieldset>
					<legend>Theme</legend>
					{#each options?.themes ?? [] as t (t.id)}
						<label class="choice">
							<input type="radio" name="theme" value={t.id} bind:group={theme} />
							<span class="swatch" style:background={t.paper} style:color={t.ink}>Aa</span>
							{t.label} <span class="quiet small">{t.font}</span>
						</label>
					{/each}
				</fieldset>
				<label class="choice"><input type="checkbox" bind:checked={cover} /> Cover page</label>
				<label class="choice"
					><input type="checkbox" bind:checked={cropMarks} /> Crop marks (for a print shop)</label
				>

				<p class="quiet small summary">
					{#if plan}{plan.page_count} pages · {trimLabel} · {photos(album?.items.length ?? 0)}{/if}
				</p>

				<section aria-labelledby="p-res" class="issues">
					<h3 id="p-res">Resolution</h3>
					{#if plan && plan.issues.length === 0}
						<p class="quiet small">Every photo has enough pixels for this size.</p>
					{/if}
					<ul>
						{#each plan?.issues ?? [] as issue, i (i)}
							{@const asset = issue.asset_id === null ? undefined : byId.get(issue.asset_id)}
							<li>
								{#if asset?.thumb}<img src={asset.thumb.url} alt="" />{/if}
								<span>
									{describe(asset)} · {Math.round(issue.ppi)} ppi ·
									{issue.level === 'block' ? 'too small to print sharply' : 'may look soft'}
								</span>
							</li>
						{/each}
					</ul>
					{#if blocking.length}
						<label class="choice">
							<input type="checkbox" bind:checked={anyway} />
							Print anyway, even if {blocking.length === 1
								? 'this photo looks'
								: 'these photos look'} soft
						</label>
					{/if}
				</section>

				{#if printError}<p role="alert">{printError}</p>{/if}
				<button class="primary" type="button" disabled={busy || !plan} onclick={download}>
					{busy ? 'Making the PDF…' : 'Download PDF'}
				</button>
			</form>

			<ul class="pages" aria-label="Pages">
				{#each pages as n (`${trim}-${theme}-${cover}-${n}`)}
					<li>
						<img
							src={api.printPreviewUrl(id, n, request, PREVIEW_PPI)}
							alt={`${pageLabel(n)} of ${plan?.page_count}`}
							loading="lazy"
						/>
						<span class="quiet small">{pageLabel(n)}</span>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>

<style>
	.page {
		padding: var(--s-5) var(--page-x) var(--s-7);
	}
	.crumb {
		margin: 0;
	}
	.crumb a {
		color: var(--ink-2);
	}
	h1 {
		margin: var(--s-4) 0 var(--s-5);
	}
	.layout {
		display: grid;
		grid-template-columns: 17rem minmax(0, 1fr);
		gap: var(--s-6);
		align-items: start;
	}
	.choices {
		display: grid;
		gap: var(--s-2);
		position: sticky;
		top: calc(var(--top) + var(--s-4));
	}
	.choices > fieldset {
		margin: var(--s-2) 0;
		display: grid;
	}
	.choices > .field {
		margin: 0;
	}
	.swatch {
		display: inline-grid;
		place-items: center;
		width: 1.75rem;
		height: 1.25rem;
		font-family: var(--font-serif);
		font-size: var(--fs-12);
		/* a paper as white as the sheet still shows: a seam of fill around it, not a line */
		box-shadow: 0 0 0 var(--fine) var(--fill);
	}
	.summary {
		margin: var(--s-1) 0 0;
	}
	.issues h3 {
		margin: var(--s-4) 0 var(--s-1);
	}
	.issues p {
		margin: 0;
	}
	.issues ul {
		list-style: none;
		margin: 0 0 var(--s-2);
		padding: 0;
		font-size: var(--fs-12);
	}
	.issues li {
		display: flex;
		gap: var(--s-2);
		align-items: center;
		padding: var(--s-1) 0;
	}
	.issues img {
		width: 2.5rem;
		height: 2.5rem;
		object-fit: contain;
		background: var(--hairline);
	}
	.primary {
		justify-self: start;
		margin-top: var(--s-3);
	}
	/* Small multiples: every page at the same scale, labelled underneath. Pages are paper on
	   the darkroom page: their own colour sets them apart, no edge, no shadow. */
	.pages {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
		gap: var(--s-5) var(--s-4);
	}
	.pages li {
		display: grid;
		gap: var(--s-2);
		justify-items: center;
	}
	.pages img {
		width: 100%;
		height: auto;
		background: var(--hairline);
	}
	@media (max-width: 1023px) {
		.layout {
			grid-template-columns: minmax(0, 1fr);
		}
		.choices {
			position: static;
		}
		.pages {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
</style>
