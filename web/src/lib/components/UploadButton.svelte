<script lang="ts">
	/**
	 * Hand-picked upload (FEATURES 10.2): choose photos, send them to your private uploads
	 * inbox with progress, then reload once the import has run. Guests can't upload.
	 */
	import { api, notice, session } from '$lib/app.svelte';
	import type { UploadResult } from '$lib/api';
	import { summarizeUpload, uploadFiles } from '$lib/upload';
	import IconButton from './ui/IconButton.svelte';

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

	/** Per request: the server takes at most 500 files in one, and small requests fail small. */
	const CHUNK = 50;
	/** Refused files named in the notice; the rest are counted. */
	const NAMED = 3;

	/**
	 * Waits for the import this upload queued, not for the whole queue (a big import of someone
	 * else's would use up the patience every time). Done, failed, or put off to a later attempt:
	 * the wait is over. If the server can't be asked, the photos are stored all the same.
	 */
	async function importDone(jobId: number) {
		const until = Date.now() + patience * 1000;
		try {
			while (Date.now() < until) {
				const job = await api.uploadJob(jobId);
				if (job.status === 'done' || job.status === 'failed' || job.run_after) return;
				await sleep(pollMs);
			}
		} catch {
			// reload now: what is imported so far shows, the rest on the next visit
		}
	}

	function summarize(result: UploadResult): string {
		const refused = result.files.filter((f) => f.outcome === 'rejected');
		if (refused.length <= NAMED) return summarizeUpload(result);
		const taken = result.files.filter((f) => f.outcome !== 'rejected');
		const named = refused.slice(0, NAMED).map((f) => `${f.name}: ${f.reason ?? 'refused'}`);
		const tail = `${refused.length} refused (${named.join(', ')}, and ${refused.length - NAMED} more)`;
		return taken.length ? `${summarizeUpload({ ...result, files: taken })}, ${tail}` : tail;
	}

	async function send(files: File[]) {
		if (!files.length) return;
		progress = 0;
		notice.show(`Uploading ${files.length} file${files.length === 1 ? '' : 's'}…`, { ms: 600_000 });
		const total = files.reduce((n, f) => n + f.size, 0) || 1;
		const result: UploadResult = { files: [], import_job_id: null };
		let bytes = 0;
		let failure: unknown = null;
		try {
			for (let at = 0; at < files.length && !failure; at += CHUNK) {
				const chunk = files.slice(at, at + CHUNK);
				const size = chunk.reduce((n, f) => n + f.size, 0);
				try {
					const part = await uploadFiles(chunk, {
						url: api.uploadUrl,
						onUnauthorized: () => session.lost(),
						onprogress: (f) => (progress = (bytes + f * size) / total)
					});
					result.files.push(...part.files);
					result.import_job_id = part.import_job_id ?? result.import_job_id;
					bytes += size;
				} catch (error) {
					failure = error;
				}
			}
			// Nothing got through: that is simply a failed upload.
			if (failure && !result.files.length) throw failure;
			let summary = summarize(result);
			if (failure) {
				const why = failure instanceof Error ? failure.message : 'the upload failed.';
				summary += `. The other ${files.length - result.files.length} were not sent: ${why}`;
			}
			if (result.import_job_id !== null) {
				notice.show(`${summary}. Adding them to the library…`, { ms: 600_000 });
				await importDone(result.import_job_id);
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
	<!-- Its name says how far an upload has got; the toast says what is happening. -->
	<IconButton
		icon="upload"
		label={progress === null ? 'Upload' : `Uploading ${Math.round(progress * 100)} %`}
		disabled={progress !== null}
		aria-busy={progress !== null}
		onclick={() => input?.click()}
	/>
{/if}
