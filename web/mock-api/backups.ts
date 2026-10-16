/** Backup places: the plan for a new one, its runs, and what its status and health say. */
import { randomBytes } from 'node:crypto';
import type { BackupHealth, BackupPlan, BackupProblem } from '../src/lib/api/types.ts';
import { admin, HttpError, idParam, nowIso, type Ctx } from './http.ts';
import { DISKS, LIBRARY_BYTES, REMOTES } from './machine.ts';
import type { MockBackup, World } from './types.ts';

const BACKUP_FOLDER = 'photo-assistant-backup';
const gb = (bytes: number) => `${(bytes / 1e9).toFixed(1)} GB`;

export const SCHEDULE =
	/^(manual|hourly|daily \d{2}:\d{2}|weekly (mon|tue|wed|thu|fri|sat|sun) \d{2}:\d{2})$/;

export function backupHelpers(h: World) {
	function settle(target: MockBackup) {
		for (const run of target.runs)
			if (run.status === 'running' && h.now() >= run.ends_at) {
				run.status = 'succeeded';
				run.finished_at = nowIso();
				if (run.kind === 'backup') {
					run.snapshot_id = randomBytes(4).toString('hex');
					run.files_new = 6;
					run.bytes_added = 31_000_000;
					run.repo_bytes = 48_231_000_000;
				} else run.details = 'restored 20 random photos and the database; all hashes match';
			}
		// the recovery guarantee: a first successful backup is proven by a restore test
		const backedUp = target.runs.some((r) => r.kind === 'backup' && r.status === 'succeeded');
		if (backedUp && !target.runs.some((r) => r.kind === 'restore_test')) {
			queueRun(target, 'restore_test');
			target.runs[0].ends_at = h.now();
			settle(target);
		}
	}

	function planFor(place: string): BackupPlan {
		const refuse = (problem: string, repository = place): BackupPlan => ({
			repository, library_bytes: LIBRARY_BYTES, free_bytes: null, ok: false, problem, warnings: []
		}); // prettier-ignore
		place = place.trim();
		if (place.startsWith('rclone:')) {
			const [remote, ...rest] = place.slice(7).split(':');
			if (!REMOTES.includes(remote) || rest.length === 0)
				return refuse('a cloud location looks like rclone:<name>:<folder>');
			const folder = rest.join(':').replace(/\/+$/, '');
			const repository = `rclone:${remote}:${folder ? `${folder}/` : ''}${BACKUP_FOLDER}`;
			return { repository, library_bytes: LIBRARY_BYTES, free_bytes: null, ok: true, problem: null, warnings: ["free space there can't be checked"] }; // prettier-ignore
		}
		if (!place.startsWith('/')) return refuse('a local backup location must be an absolute path');
		const repository = `${place.replace(/\/+$/, '')}/${BACKUP_FOLDER}`;
		if (h.state().backups.some((b) => b.repository === repository))
			return refuse('there is already a backup in this folder, made with another key: choose another', repository); // prettier-ignore
		const disk = DISKS.find((d) => place === d.path || place.startsWith(`${d.path}/`));
		const home = place.startsWith('/home/');
		if (!disk && !home) return refuse(`${place} does not exist: is the disk plugged in?`, repository); // prettier-ignore
		const free = disk ? disk.free_bytes : 120_000_000_000;
		if (free < LIBRARY_BYTES)
			return { ...refuse(`not enough room: the library is ${gb(LIBRARY_BYTES)} and only ${gb(free)} is free there (${gb(LIBRARY_BYTES - free)} missing)`, repository), free_bytes: free }; // prettier-ignore
		const warnings = home ? ['this is the same disk as the library: it guards against mistakes, not against the disk failing'] : []; // prettier-ignore
		return { repository, library_bytes: LIBRARY_BYTES, free_bytes: free, ok: true, problem: null, warnings }; // prettier-ignore
	}

	function targetOut(target: MockBackup) {
		settle(target);
		const { runs, ...rest } = target;
		const lastBackup = runs.find((r) => r.kind === 'backup'); // as the real status: backups only
		const lastRun = lastBackup ? (({ ends_at: _e, ...r }) => r)(lastBackup) : null;
		const lastSuccess = runs.find((r) => r.status === 'succeeded' && r.kind === 'backup');
		const overdue = target.enabled && !lastSuccess;
		const lastTest = runs.find((r) => r.kind === 'restore_test');
		const proven = runs.find((r) => r.kind === 'restore_test' && r.status === 'succeeded');
		const { key: _k, key_saved, mirror_path = null, mirrored_at = null, ...shown } = rest;
		const failing = lastRun?.status === 'failed' || lastTest?.status === 'failed';
		return {
			...shown,
			key_saved,
			mirror_path,
			last_mirror_at: mirror_path ? mirrored_at : null,
			mirror_error: null,
			mirror_overdue: false,
			skipped_since: null,
			last_proven_at: proven?.finished_at ?? null,
			restore_failing: lastTest?.status === 'failed',
			last_success_at: lastSuccess?.finished_at ?? null,
			last_run: lastRun,
			repo_bytes: runs.find((r) => r.repo_bytes)?.repo_bytes ?? null,
			next_run_at: target.enabled && target.schedule !== 'manual' ? '2026-10-03T02:30:00' : null,
			overdue,
			needs_attention: target.enabled && (overdue || failing || !key_saved)
		};
	}

	/** As the real one: each enabled target is a place, plus its Proton copy; alerts come first. */
	function healthOut(): BackupHealth {
		const places = h
			.state()
			.backups.filter((b) => b.enabled)
			.map(targetOut);
		const flags = places.flatMap((t) => [
			t.last_success_at !== null && !t.overdue && t.last_run?.status !== 'failed' && !t.restore_failing,
			...(t.mirror_path ? [t.last_mirror_at !== null] : [])
		]); // prettier-ignore
		const ok = flags.filter(Boolean).length;
		const problems: BackupProblem[] = [];
		if (flags.length === 0)
			problems.push({
				severity: 'warning',
				message: 'No backup is set up: the photos exist only on this computer. Add two backup places.',
				target_id: null,
				error_kind: null
			}); // prettier-ignore
		else if (flags.length === 1)
			problems.push({
				severity: 'warning',
				message: 'Only one backup place is set up: add a second, so one lost disk is not the end of the photos.',
				target_id: null,
				error_kind: null
			}); // prettier-ignore
		else if (ok < 2)
			problems.push({
				severity: 'alert',
				message: `Only ${ok} of ${flags.length} backup places is up to date.`,
				target_id: null,
				error_kind: null
			});
		for (const t of places) {
			if (t.last_run?.status === 'failed')
				problems.push({
					severity: 'alert',
					message: `${t.label}: the last backup failed: ${t.last_run.error ?? 'no reason given'}`,
					target_id: t.id,
					error_kind: t.last_run.error_kind ?? 'unknown'
				});
			if (t.restore_failing)
				problems.push({
					severity: 'alert',
					message: `${t.label}: the last restore test failed. Open Backups and run it again.`,
					target_id: t.id,
					error_kind: null
				});
			if (t.overdue && t.last_run?.status !== 'failed')
				problems.push({ severity: 'warning', message: `${t.label}: the backup is overdue.`, target_id: t.id, error_kind: null }); // prettier-ignore
			if (!t.key_saved)
				problems.push({
					severity: 'warning',
					message: `${t.label}: the recovery key is not saved yet. Without it this backup cannot be read.`,
					target_id: t.id,
					error_kind: null
				});
		}
		problems.sort((a, b) => Number(a.severity === 'warning') - Number(b.severity === 'warning'));
		return { protected: ok >= 2, places_ok: ok, places_total: flags.length, problems };
	}

	function findBackup(ctx: Ctx) {
		admin(ctx);
		const target = h.state().backups.find((b) => b.id === idParam(ctx));
		if (!target) throw new HttpError(404, 'backup target not found');
		return target;
	}

	function queueRun(target: MockBackup, kind: 'backup' | 'restore_test') {
		const state = h.state();
		const id = Math.max(0, ...state.backups.flatMap((b) => b.runs.map((r) => r.id))) + 1;
		target.runs.unshift({
			id,
			kind,
			status: 'running',
			started_at: nowIso(),
			finished_at: null,
			snapshot_id: null,
			bytes_added: null,
			files_new: null,
			repo_bytes: null,
			error: null,
			error_kind: null,
			details: null,
			ends_at: h.now() + 3000
		});
		return { job_id: state.nextId.job++, target_id: target.id };
	}

	return { settle, planFor, targetOut, healthOut, findBackup, queueRun };
}
