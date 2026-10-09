/** Import jobs: queued, then running, then done with a report, as the clock moves. */
import { nowIso } from './http.ts';
import { makeAsset, PLACES, rng } from './library.ts';
import type { MockAsset, World } from './types.ts';

export function jobHelpers(h: World) {
	/** Jobs advance with the clock: queued 0.8 s, running until 3 s, then done. */
	function advanceJobs() {
		const t = h.now();
		for (const job of h.state().jobs) {
			if (job.status === 'done' || job.status === 'failed' || job.run_at === 0) continue;
			const age = t - job.run_at;
			if (age < 800) job.status = 'queued';
			else if (age < 3000) {
				job.status = 'running';
				if (job.kind === 'import') importProgress(Number(job.payload.source_id), age);
			} else {
				job.status = 'done';
				if (job.kind === 'import') finishImport(Number(job.payload.source_id));
			}
		}
	}

	/** A running import run whose counts grow, like the real one's (live progress). */
	function importProgress(sourceId: number, age: number) {
		if (
			h
				.state()
				.sources.find((s) => s.id === sourceId)
				?.path.includes('gone')
		)
			return;
		const seen = Math.max(1, Math.round(((age - 800) / 2200) * 11));
		let run = h.state().reports.find((r) => r.source_id === sourceId && r.status === 'running');
		if (!run) {
			run = {
				id: h.state().nextId.run++,
				source_id: sourceId,
				status: 'running',
				started_at: nowIso(),
				finished_at: null,
				message: null,
				summary: { imported: 0, duplicate: 0, already_known: 0, skipped: 0, failed: 0, ignored: 0, files_seen: 0 }, // prettier-ignore
				items: []
			};
			h.state().reports.unshift(run);
		}
		run.summary = { ...run.summary, files_seen: seen, imported: Math.max(0, seen - 2) };
	}

	function finishImport(sourceId: number) {
		const source = h.state().sources.find((s) => s.id === sourceId);
		if (!source) return;
		h.state().reports = h
			.state()
			.reports.filter((r) => !(r.source_id === sourceId && r.status === 'running'));
		if (source.path.includes('gone')) {
			// A folder that was there when added and has gone since (an unplugged disk).
			const zero = { imported: 0, duplicate: 0, already_known: 0, skipped: 0, failed: 0 };
			h.state().reports.unshift({
				id: h.state().nextId.run++,
				source_id: sourceId,
				status: 'failed',
				started_at: nowIso(),
				finished_at: nowIso(),
				message: `folder not found on this machine: ${source.path}`,
				summary: { ...zero, ignored: 0, files_seen: 0 },
				items: []
			});
			return;
		}
		const r = rng(h.state().nextId.run * 7919);
		const fresh = source.path.includes('empty') ? 0 : 6;
		const added: MockAsset[] = [];
		for (let i = 0; i < fresh; i++) {
			const t = new Date(Date.UTC(2026, 8, 20 + (i % 5), 10 + i));
			const asset = makeAsset(h.state().nextId.asset++, t, r.pick(PLACES), 'phone', r);
			asset.sources = [{ source_id: sourceId, relative_path: `new/IMG_${asset.id}.HEIC` }];
			added.push(asset);
		}
		h.state().assets.push(...added);
		const items = [
			...added.map((a) => ({
				relative_path: a.sources[0].relative_path,
				outcome: 'imported' as const,
				reason: null,
				asset_id: a.id
			})),
			{
				relative_path: 'new/IMG_0501.MOV',
				outcome: 'skipped' as const,
				reason: 'video (not supported yet)',
				asset_id: null
			},
			{
				relative_path: 'new/broken.jpg',
				outcome: 'failed' as const,
				reason: 'file is corrupt: JPEG ends early',
				asset_id: null
			},
			{
				relative_path: 'new/copy of IMG_0001.JPG',
				outcome: 'duplicate' as const,
				reason: 'same content as IMG_0001.JPG (Phone)',
				asset_id: 1
			}
		];
		const summary = {
			imported: added.length,
			duplicate: 1,
			already_known: 0,
			skipped: 1,
			failed: 1,
			ignored: 2,
			files_seen: added.length + 5
		};
		h.state().reports.unshift({
			id: h.state().nextId.run++,
			source_id: sourceId,
			status: 'done',
			started_at: nowIso(),
			finished_at: nowIso(),
			message: null,
			summary,
			items
		});
	}

	function queueScan(sourceId: number) {
		const job = {
			id: h.state().nextId.job++,
			kind: 'import',
			payload: { source_id: sourceId },
			status: 'queued' as const,
			attempts: 0,
			error: null,
			run_after: null,
			run_at: h.now()
		};
		h.state().jobs.push(job);
		return { job_id: job.id, source_id: sourceId };
	}

	return { advanceJobs, queueScan };
}
