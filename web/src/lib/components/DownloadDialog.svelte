<script lang="ts" module>
	import type { DownloadRequest } from '$lib/api';
	import { frameError } from '$lib/download';

	let frames = 0;

	/**
	 * Start a download in a hidden frame, so the browser writes the stream straight to disk
	 * instead of holding it in memory. A ZIP is a real form POST whose one field, `request`,
	 * holds the DownloadRequest JSON (docs/contracts/api-v1.md); a single photo is a GET.
	 * When the server refuses, the frame loads its JSON answer instead of saving a file:
	 * `onerror` then gets the server's sentence.
	 */
	export function startDownload(
		target: { post: string; request: DownloadRequest } | { get: string },
		onerror: (detail: string) => void
	) {
		const frame = document.createElement('iframe');
		frame.name = `pa-download-${++frames}`;
		frame.title = 'Download';
		frame.hidden = true;
		frame.addEventListener('load', () => {
			let text: string | null;
			try {
				text = frame.contentDocument?.body?.innerText ?? null;
			} catch {
				// a cross-origin page (should not happen): treat as an error below
				text = '{}';
			}
			const detail = frameError(text);
			if (detail) onerror(detail);
		});
		document.body.append(frame);
		// A saved download never loads the frame; keep it a while so a slow stream isn't cut.
		setTimeout(() => frame.remove(), 30 * 60_000);
		if ('get' in target) {
			frame.src = target.get;
			return;
		}
		const form = document.createElement('form');
		form.method = 'POST';
		form.action = target.post;
		form.target = frame.name;
		form.hidden = true;
		const field = document.createElement('input');
		field.type = 'hidden';
		field.name = 'request';
		field.value = JSON.stringify(target.request);
		form.append(field);
		document.body.append(form);
		form.submit();
		form.remove();
	}
</script>

<script lang="ts">
	import type { AssetOut, DownloadEstimate, DownloadOptions, DownloadScope } from '$lib/api';
	import { api, notice, photoShare, SHARE_AGAIN, viewport } from '$lib/app.svelte';
	import {
		DEFAULT_OPTIONS,
		EDGE_PRESETS,
		applySimple,
		buildDownloadRequest,
		scopeLabel,
		simpleChoices,
		simpleOf
	} from '$lib/download';
	import { errorMessage, formatBytes } from '$lib/format';
	import { canShare } from '$lib/share';
	import Dialog from './Dialog.svelte';

	type Props = {
		scope: DownloadScope;
		single?: AssetOut;
		/** Some of the photos have edits (which an original file does not include). */
		edited?: boolean;
		onclose: () => void;
	};
	let { scope, single, edited = false, onclose }: Props = $props();

	let options = $state<DownloadOptions>({ ...DEFAULT_OPTIONS });
	let custom = $state(false);
	let more = $state(false);
	let estimate = $state<DownloadEstimate | null>(null);
	let estimateError = $state('');
	let error = $state('');
	let busy = $state(false);
	const lossy = $derived(options.format === 'jpeg' || options.format === 'webp');
	const request = $derived(buildDownloadRequest(scope, options));
	const hasEdits = $derived(single ? single.edited : edited);
	const nothing = $derived(estimate?.count === 0);
	const simple = $derived(custom ? null : simpleOf(options));

	$effect(() => {
		const body = request;
		let stale = false;
		estimate = null;
		estimateError = '';
		const timer = setTimeout(() => {
			api
				.estimateDownload(body)
				.then((e) => !stale && (estimate = e))
				.catch((e: unknown) => {
					if (!stale) estimateError = errorMessage(e, 'Could not estimate.');
				});
		}, 200);
		return () => {
			stale = true;
			clearTimeout(timer);
		};
	});

	function singleUrl(asset: AssetOut) {
		return api.singleDownloadUrl(asset.id, options);
	}

	const canShareFiles = () => viewport.phone && canShare();

	async function share(asset: AssetOut) {
		busy = true;
		try {
			const outcome = await photoShare.share(asset, options);
			if (outcome === 'shared') onclose();
			else if (outcome === 'ready') notice.show(SHARE_AGAIN);
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	/** The frame showed an error: say so, and find out whether the session ran out. */
	function failed(detail: string) {
		notice.show(`The download did not start: ${detail}`, { ms: 10_000 });
		api.me().catch(() => undefined); // a 401 here sends the user to sign in
	}

	/**
	 * Check first (session, rights, server health) with the estimate, so a refusal shows up
	 * here as a sentence instead of a download that silently never starts.
	 */
	async function download() {
		busy = true;
		error = '';
		try {
			const checked = await api.estimateDownload(request);
			if (checked.count === 0) {
				estimate = checked;
				return;
			}
		} catch (e) {
			error = errorMessage(e, 'Could not start the download.');
			return;
		} finally {
			busy = false;
		}
		if (single) startDownload({ get: singleUrl(single) }, failed);
		else {
			startDownload({ post: api.downloadAction, request }, failed);
			notice.show('Download started. Your browser saves the ZIP as it arrives.');
		}
		onclose();
	}
</script>

<Dialog title={single ? 'Download photo' : 'Download'} {onclose}>
	<p class="summary" aria-live="polite">
		{#if estimate && nothing}
			<span id="dl-nothing">
				You may view {single ? 'this photo' : 'these photos'} but not download {single
					? 'it'
					: 'them'}: downloading needs access to the folder a photo comes from. An album shared with
				you only lets you see its photos.
			</span>
		{:else if estimate}
			{single ? '1 photo' : scopeLabel(scope, estimate.count)}
			<span class="quiet"
				>· about {formatBytes(
					estimate.bytes
				)}{#if !single && 'ids' in scope && estimate.count < scope.ids.length}
					· {scope.ids.length - estimate.count} you may only view are left out{/if}</span
			>
		{:else if estimateError}
			<span class="quiet">{estimateError}</span>
		{:else}
			<span class="quiet">Estimating…</span>
		{/if}
	</p>

	<fieldset class="plain">
		<legend class="visually-hidden">What to download</legend>
		{#each simpleChoices(hasEdits) as pick (pick.value)}
			<label class="pick">
				<input
					type="radio"
					name="simple"
					aria-labelledby={`dl-${pick.value}`}
					aria-describedby={`dl-${pick.value}-about`}
					checked={simple === pick.value}
					onchange={() => {
						custom = false;
						options = applySimple(options, pick.value);
					}}
				/>
				<span id={`dl-${pick.value}`}>{pick.label}</span>
				<span id={`dl-${pick.value}-about`} class="quiet small about">{pick.about}</span>
			</label>
		{/each}
	</fieldset>
	<label class="choice">
		<input
			type="checkbox"
			bind:checked={options.strip_location}
			disabled={options.strip_all_metadata}
		/>
		Remove location
	</label>

	<button
		type="button"
		class="more"
		aria-expanded={more}
		aria-controls="dl-more"
		onclick={() => (more = !more)}>More options</button
	>
	{#if more}
		<div id="dl-more">
			<fieldset>
				<legend>Format</legend>
				{#each [['original', 'Original file (without edits)'], ['jpeg', 'JPEG'], ['png', 'PNG'], ['webp', 'WebP']] as [value, label] (value)}
					<label class="choice">
						<input type="radio" name="format" {value} bind:group={options.format} />
						{label}
					</label>
				{/each}
				{#if hasEdits && options.format === 'original'}
					<p class="quiet small note">
						{single ? 'This photo has' : 'Some of these photos have'} edits; an original file comes as
						it was taken. Choose JPEG to include the edits.
					</p>
				{/if}
			</fieldset>

			{#if lossy}
				<label class="row">
					Quality <span class="value">{options.quality}</span>
					<input type="range" min="1" max="100" bind:value={options.quality} />
				</label>
			{/if}

			<fieldset>
				<legend>Size (long edge)</legend>
				{#each EDGE_PRESETS as preset (preset.label)}
					<label class="choice">
						<input
							type="radio"
							name="edge"
							checked={!custom && options.max_edge === preset.value}
							onchange={() => {
								custom = false;
								options.max_edge = preset.value;
							}}
						/>
						{preset.label}
					</label>
				{/each}
				<label class="choice">
					<input type="radio" name="edge" checked={custom} onchange={() => (custom = true)} />
					Custom
				</label>
				{#if custom}
					<label class="row">
						Pixels
						<input
							type="number"
							min="100"
							max="20000"
							step="1"
							value={options.max_edge ?? 1600}
							oninput={(e) => (options.max_edge = Number(e.currentTarget.value) || null)}
						/>
					</label>
				{/if}
				<p class="quiet small">Never enlarged beyond the original.</p>
			</fieldset>

			<fieldset>
				<legend>Metadata</legend>
				<label class="choice">
					<input type="checkbox" bind:checked={options.strip_all_metadata} />
					Remove all metadata
				</label>
			</fieldset>

			{#if !single}
				<fieldset>
					<legend>In the ZIP</legend>
					<label class="row">
						Names
						<select bind:value={options.naming}>
							<option value="name">Photo names</option>
							<option value="original">Original file names</option>
							<option value="date">Date and place</option>
						</select>
					</label>
					<label class="row">
						Folders
						<select bind:value={options.folders}>
							<option value="flat">None</option>
							<option value="year">By year</option>
							<option value="month">By month</option>
						</select>
					</label>
				</fieldset>
			{/if}
		</div>
	{/if}
	{#if error}<p role="alert">{error}</p>{/if}

	{#snippet actions()}
		{#if single && canShareFiles() && !nothing}
			<button type="button" disabled={busy} onclick={() => share(single)}>Save to Photos</button>
		{/if}
		<button
			class="primary"
			type="button"
			disabled={nothing || busy}
			aria-describedby={nothing ? 'dl-nothing' : undefined}
			onclick={download}
		>
			Download
		</button>
	{/snippet}
</Dialog>

<style>
	.summary {
		margin: 0 0 var(--s-2);
	}
	.note {
		margin: var(--s-1) 0 0;
	}
	.plain {
		margin-top: var(--s-2);
	}
	/* A plain choice: the option, and under it what you get. The whole block is the target. */
	.pick {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		column-gap: var(--s-2);
		align-items: center;
		padding: var(--s-2) 0;
	}
	.about {
		grid-column: 2;
	}
	.more {
		display: block;
		margin: var(--s-3) 0 0;
		padding: 0;
		border: 0;
		background: none;
		color: var(--ink-2);
		text-decoration: underline;
		text-underline-offset: 0.2em;
	}
	.more[aria-expanded='true'] {
		color: var(--ink);
	}
	@media (pointer: coarse) {
		.more {
			min-height: var(--target);
		}
	}
	.row {
		display: grid;
		grid-template-columns: 5rem auto 1fr;
		align-items: center;
		gap: var(--s-2);
		margin-top: var(--s-1);
	}
	.row select,
	.row input[type='number'] {
		grid-column: 2 / 4;
	}
	.value {
		min-width: 2rem;
		color: var(--ink);
	}
	fieldset .small {
		margin: var(--s-1) 0 0;
	}
</style>
