<script lang="ts">
	/**
	 * Hand-picked upload (FEATURES 10.2): choose photos, send them to your private uploads
	 * inbox with progress, then reload once the import has run. Guests can't upload.
	 */
	import { api, notice, session } from '$lib/app.svelte';
	import { summarizeUpload, uploadFiles } from '$lib/upload';

	type Props = {
		onuploaded?: () => void;
		/** Seconds to wait for the import job before reloading anyway. */
		patience?: number;
		pollMs?: number;
	};
	let { onuploaded, patience = 60, pollMs = 1000 }: Props = $props();

	let input: HTMLInputElement | undefined = $state();
	let progress = $state<number | null>(null);

	const ACCEPT = 'image/*,.heic,.heif,.dng,.cr2,.cr3,.nef,.arw,.raf,.orf,.rw2';
	const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

	async function importDone() {
		const until = Date.now() + patience * 1000;
		while (Date.now() < until) {
			const { jobs } = await api.stats();
			if (jobs.queued + jobs.running === 0) return;
			await sleep(pollMs);
		}
	}

	async function send(files: File[]) {
		if (!files.length) return;
		progress = 0;
		notice.show(`Uploading ${files.length} file${files.length === 1 ? '' : 's'}…`, { ms: 600_000 });
		try {
			const result = await uploadFiles(files, {
				url: api.uploadUrl,
				onprogress: (f) => (progress = f)
			});
			const summary = summarizeUpload(result);
			if (result.import_job_id !== null) {
				notice.show(`${summary}. Adding them to the library…`, { ms: 600_000 });
				await importDone();
			}
			notice.show(summary, { ms: 8000 });
			onuploaded?.();
		} catch (error) {
			notice.error(error);
		} finally {
			progress = null;
			if (input) input.value = '';
		}
	}
</script>

{#if session.canEdit}
	<input
		bind:this={input}
		class="visually-hidden"
		type="file"
		multiple
		accept={ACCEPT}
		tabindex="-1"
		aria-label="Photos to upload"
		onchange={() => send([...(input?.files ?? [])])}
	/>
	<button
		type="button"
		disabled={progress !== null}
		aria-busy={progress !== null}
		onclick={() => input?.click()}
	>
		{progress === null ? 'Upload' : `Uploading ${Math.round(progress * 100)} %`}
	</button>
{/if}
