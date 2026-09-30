<script lang="ts" module>
	import type { DownloadRequest } from '$lib/api';

	const FRAME = 'pa-download-frame';

	/**
	 * Start a streamed ZIP download: a real form POST into a hidden iframe, so the browser
	 * writes the stream straight to disk instead of holding it in memory. The body is one
	 * field, `request`, holding the DownloadRequest JSON (see docs/wiring/web.md).
	 */
	export function postDownload(action: string, request: DownloadRequest) {
		if (!document.querySelector(`iframe[name="${FRAME}"]`)) {
			const frame = document.createElement('iframe');
			frame.name = FRAME;
			frame.title = 'Downloads';
			frame.hidden = true;
			document.body.append(frame);
		}
		const form = document.createElement('form');
		form.method = 'POST';
		form.action = action;
		form.target = FRAME;
		form.hidden = true;
		const field = document.createElement('input');
		field.type = 'hidden';
		field.name = 'request';
		field.value = JSON.stringify(request);
		form.append(field);
		document.body.append(form);
		form.submit();
		form.remove();
	}
</script>

<script lang="ts">
	import type { AssetOut, DownloadEstimate, DownloadOptions, DownloadScope } from '$lib/api';
	import { api, notice, viewport } from '$lib/app.svelte';
	import {
		DEFAULT_OPTIONS,
		EDGE_PRESETS,
		buildDownloadRequest,
		scopeLabel,
		singleFileName
	} from '$lib/download';
	import { formatBytes } from '$lib/format';
	import Dialog from './Dialog.svelte';

	type Props = { scope: DownloadScope; single?: AssetOut; onclose: () => void };
	let { scope, single, onclose }: Props = $props();

	let options = $state<DownloadOptions>({ ...DEFAULT_OPTIONS });
	let custom = $state(false);
	let estimate = $state<DownloadEstimate | null>(null);
	let estimateError = $state('');
	let busy = $state(false);
	const lossy = $derived(options.format === 'jpeg' || options.format === 'webp');
	const request = $derived(buildDownloadRequest(scope, options));
	const count = new Intl.NumberFormat('en-GB');

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
					if (!stale) estimateError = e instanceof Error ? e.message : 'Could not estimate.';
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

	function canShareFiles(): boolean {
		try {
			const probe = new File([''], 'probe.jpg', { type: 'image/jpeg' });
			return viewport.phone && !!navigator.canShare?.({ files: [probe] });
		} catch {
			return false;
		}
	}

	async function share(asset: AssetOut) {
		busy = true;
		try {
			const response = await fetch(singleUrl(asset), { credentials: 'same-origin' });
			if (!response.ok) throw new Error(`The library server answered ${response.status}.`);
			const blob = await response.blob();
			const file = new File([blob], singleFileName(asset.id, asset.taken_at, options.format), {
				type: blob.type
			});
			await navigator.share({ files: [file] });
			onclose();
		} catch (e) {
			if (!(e instanceof DOMException && e.name === 'AbortError')) notice.error(e);
		} finally {
			busy = false;
		}
	}

	function download() {
		if (single) {
			const a = document.createElement('a');
			a.href = singleUrl(single);
			a.download = singleFileName(single.id, single.taken_at, options.format);
			document.body.append(a);
			a.click();
			a.remove();
		} else {
			postDownload(api.downloadAction, request);
			notice.show('Download started. Your browser saves the ZIP as it arrives.');
		}
		onclose();
	}
</script>

<Dialog title={single ? 'Download photo' : 'Download'} {onclose}>
	<p class="summary" aria-live="polite">
		{#if single}
			1 photo
		{:else}
			{scopeLabel(scope, estimate?.count)}
		{/if}
		<span class="quiet">
			{#if estimate}· {count.format(estimate.count)} photo{estimate.count === 1 ? '' : 's'}, about {formatBytes(
					estimate.bytes
				)}{:else if estimateError}· {estimateError}{:else}· estimating…{/if}
		</span>
	</p>

	<fieldset>
		<legend>Format</legend>
		{#each [['original', 'Original file'], ['jpeg', 'JPEG'], ['png', 'PNG'], ['webp', 'WebP']] as [value, label] (value)}
			<label class="choice">
				<input type="radio" name="format" {value} bind:group={options.format} />
				{label}
			</label>
		{/each}
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
			<input
				type="checkbox"
				bind:checked={options.strip_location}
				disabled={options.strip_all_metadata}
			/>
			Remove location
		</label>
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

	{#snippet actions()}
		{#if single && canShareFiles()}
			<button type="button" disabled={busy} onclick={() => share(single)}>Save to Photos</button>
		{/if}
		<button class="primary" type="button" disabled={estimate?.count === 0} onclick={download}>
			Download
		</button>
	{/snippet}
</Dialog>

<style>
	.summary {
		margin: 0 0 0.5rem;
	}
	fieldset {
		border: 0;
		padding: 0;
		margin: 0.9rem 0 0;
	}
	legend {
		font-size: var(--fs-12);
		color: var(--ink-2);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 0;
		margin-bottom: 0.25rem;
	}
	.choice {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		margin: 0.15rem 1rem 0.15rem 0;
		color: var(--ink);
	}
	.row {
		display: grid;
		grid-template-columns: 5rem auto 1fr;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.4rem;
	}
	.row select,
	.row input[type='number'] {
		grid-column: 2 / 4;
	}
	.value {
		min-width: 2rem;
		color: var(--ink);
	}
</style>
