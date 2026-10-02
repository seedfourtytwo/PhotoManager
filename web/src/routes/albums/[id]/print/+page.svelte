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
			.catch(
				(e: unknown) => (error = e instanceof Error ? e.message : 'Could not open the album.')
			);
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
				if (!stale) error = e instanceof Error ? e.message : 'Could not plan the pages.';
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
				`Saved ${pdf.filename}${pdf.warnings ? ` (${pdf.warnings} photo${pdf.warnings === 1 ? '' : 's'} may look soft)` : ''}.`
			);
		} catch (e) {
			printError =
				e instanceof ApiError && e.status === 422 && blocking.length
					? `${e.message}. Choose a smaller size, take those photos out, or tick “Print anyway”.`
					: e instanceof Error
						? e.message
						: 'Could not make the PDF.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Print {album?.title ?? 'album'} · Photos</title></svelte:head>

<div class="page">
	<p class="small"><a class="quiet" href={`/albums/${id}`}>{album?.title ?? 'Album'}</a></p>
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
					{#if plan}{plan.page_count} pages · {trimLabel} · {album?.items.length ?? 0} photos{/if}
				</p>

				<section aria-labelledby="p-res" class="issues">
					<h2 id="p-res">Resolution</h2>
					{#if plan && plan.issues.length === 0}
						<p class="quiet small">Every photo has enough pixels for this size.</p>
					{/if}
					<ul>
						{#each plan?.issues ?? [] as issue (issue.asset_id ?? issue.ppi)}
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
		padding: 1rem 0.75rem 3rem;
	}
	h1 {
		font-size: var(--fs-28);
		margin-bottom: 1rem;
	}
	.layout {
		display: grid;
		grid-template-columns: 18rem minmax(0, 1fr);
		gap: 2rem;
		align-items: start;
	}
	.choices {
		display: grid;
		gap: 0.6rem;
		position: sticky;
		top: 1rem;
	}
	.field {
		display: grid;
		gap: 0.15rem;
	}
	fieldset {
		border: 0;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.25rem;
	}
	legend {
		color: var(--ink-2);
		margin-bottom: 0.25rem;
		padding: 0;
	}
	.choice {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		color: var(--ink);
	}
	.swatch {
		display: inline-grid;
		place-items: center;
		width: 1.6rem;
		height: 1.2rem;
		font-family: var(--font-text);
		font-size: var(--fs-12);
		border: 1px solid var(--hairline);
	}
	.summary {
		margin: 0.25rem 0 0;
	}
	h2 {
		font-size: var(--fs-12);
		color: var(--ink-2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 0.5rem 0 0.25rem;
	}
	.issues ul {
		list-style: none;
		margin: 0 0 0.5rem;
		padding: 0;
		font-size: var(--fs-12);
		max-height: 14rem;
		overflow-y: auto;
	}
	.issues li {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		padding: 0.15rem 0;
	}
	.issues img {
		width: 2.5rem;
		height: 2.5rem;
		object-fit: contain;
		background: var(--hairline);
	}
	.primary {
		justify-self: start;
	}
	/* Small multiples: every page at the same scale, labelled underneath. */
	.pages {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
		gap: 1.25rem 1rem;
	}
	.pages li {
		display: grid;
		gap: 0.25rem;
		justify-items: center;
	}
	.pages img {
		width: 100%;
		height: auto;
		background: var(--hairline);
		box-shadow: 0 0 0 1px var(--hairline);
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
