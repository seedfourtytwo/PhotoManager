/** Backups (admin): setting a place up, its recovery key, its Proton copy, its runs. */
import { randomBytes } from 'node:crypto';
import type { BackupPatch } from '../../src/lib/api/types.ts';
import { backupHelpers, SCHEDULE } from '../backups.ts';
import { admin, HttpError, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import { DISKS, LIBRARY_BYTES, REMOTES } from '../machine.ts';
import type { MockBackup } from '../types.ts';

export function backupRoutes(h: Helpers): Route[] {
	const { settle, planFor, targetOut, healthOut, findBackup, queueRun } = backupHelpers(h);

	return [
		['GET', /^\/api\/backups$/, (ctx) => (admin(ctx), ok(h.state().backups.map(targetOut)))],
		['GET', /^\/api\/backups\/health$/, (ctx) => (admin(ctx), ok(healthOut()))],
		[
			'POST',
			/^\/api\/backups$/,
			(ctx) => {
				admin(ctx);
				const body = requireFields<{ label: string; repository: string; password_file: string; schedule?: string; quiet_window?: string | null; retention?: Record<string, number> }>(ctx.body, ['label', 'repository', 'password_file']); // prettier-ignore
				const schedule = body.schedule ?? 'daily 02:30';
				if (!SCHEDULE.test(schedule))
					throw new HttpError(422, `unknown schedule '${schedule}': use 'manual', 'hourly', 'daily HH:MM' or 'weekly sun HH:MM'`); // prettier-ignore
				if (h.state().backups.some((b) => b.label === body.label))
					throw new HttpError(409, `a backup target named '${body.label}' already exists`);
				const target: MockBackup = {
					id: Math.max(0, ...h.state().backups.map((b) => b.id)) + 1,
					label: body.label,
					kind: body.repository.startsWith('rclone:') ? 'rclone' : 'local',
					repository: body.repository,
					schedule,
					quiet_window: body.quiet_window ?? null,
					retention: body.retention ?? { daily: 7, weekly: 4, monthly: 12 },
					enabled: true,
					key: '',
					key_saved: true,
					runs: []
				};
				h.state().backups.push(target);
				return ok(targetOut(target), 201);
			}
		],
		[
			'GET',
			/^\/api\/backups\/places$/,
			(ctx) => (admin(ctx), ok({ library_bytes: LIBRARY_BYTES, disks: DISKS, remotes: REMOTES }))
		],
		[
			'POST',
			/^\/api\/backups\/plan$/,
			(ctx) => (
				admin(ctx),
				ok(planFor(requireFields<{ place: string }>(ctx.body, ['place']).place))
			)
		],
		[
			'POST',
			/^\/api\/backups\/setup$/,
			(ctx) => {
				admin(ctx);
				const body = requireFields<{ label: string; place: string; schedule?: string }>(ctx.body, ['label', 'place']); // prettier-ignore
				const label = body.label.trim();
				const schedule = body.schedule ?? 'daily 02:30';
				const plan = planFor(body.place);
				if (plan.problem) throw new HttpError(422, plan.problem);
				if (!label) throw new HttpError(422, 'a backup target needs a name');
				if (!SCHEDULE.test(schedule)) throw new HttpError(422, `unknown schedule '${schedule}'`);
				if (h.state().backups.some((b) => b.label.toLowerCase() === label.toLowerCase()))
					throw new HttpError(409, `a backup target named '${label}' already exists`);
				const target: MockBackup = {
					id: Math.max(0, ...h.state().backups.map((b) => b.id)) + 1,
					label,
					kind: plan.repository.startsWith('rclone:') ? 'rclone' : 'local',
					repository: plan.repository,
					schedule,
					quiet_window: null,
					retention: { daily: 7, weekly: 4, monthly: 12 },
					enabled: true,
					key: randomBytes(32).toString('base64url'),
					key_saved: false,
					runs: []
				};
				h.state().backups.push(target);
				queueRun(target, 'backup');
				const recovery = { label, repository: target.repository, key: target.key };
				return ok({ target: targetOut(target), recovery }, 201);
			}
		],
		[
			'GET',
			/^\/api\/backups\/(\d+)\/recovery$/,
			(ctx) => {
				const target = findBackup(ctx);
				if (!target.key) throw new HttpError(409, `the key file is gone: /home/c/.restic-pass`);
				return ok({ label: target.label, repository: target.repository, key: target.key });
			}
		],
		[
			'POST',
			/^\/api\/backups\/(\d+)\/key-saved$/,
			(ctx) => {
				const target = findBackup(ctx);
				target.key_saved = true;
				return ok(targetOut(target));
			}
		],
		[
			'PUT',
			/^\/api\/backups\/(\d+)\/proton-copy$/,
			(ctx) => {
				const target = findBackup(ctx);
				const { path } = (ctx.body ?? {}) as { path?: string | null };
				if (path) {
					if (target.kind !== 'local')
						throw new HttpError(422, 'only a backup in a folder or disk of this machine can be copied'); // prettier-ignore
					h.protonPlace(path, false);
				}
				target.mirror_path = path ?? null;
				// as the real one: the first copy follows at once when there is a backup to copy
				const backedUp = target.runs.some((r) => r.kind === 'backup' && r.status === 'succeeded');
				target.mirrored_at = path && backedUp ? new Date().toISOString() : null;
				return ok(targetOut(target));
			}
		],
		[
			'PATCH',
			/^\/api\/backups\/(\d+)$/,
			(ctx) => {
				const target = findBackup(ctx);
				const body = (ctx.body ?? {}) as BackupPatch & Record<string, unknown>;
				const unknown = Object.keys(body).filter(
					(k) => !['enabled', 'schedule', 'quiet_window', 'retention'].includes(k)
				);
				if (unknown.length) throw new HttpError(422, `extra fields not permitted: ${unknown}`);
				if ('schedule' in body && !SCHEDULE.test(body.schedule ?? ''))
					throw new HttpError(422, `unknown schedule '${body.schedule}': use 'manual', 'hourly', 'daily HH:MM' or 'weekly sun HH:MM'`); // prettier-ignore
				if (body.quiet_window && !/^\d{2}:\d{2}-\d{2}:\d{2}$/.test(body.quiet_window))
					throw new HttpError(422, `quiet window '${body.quiet_window}' must look like 22:00-06:00`); // prettier-ignore
				const retention = { ...target.retention, ...body.retention };
				const counts = Object.values(retention);
				if (counts.some((v) => v < 0) || !counts.some((v) => v > 0))
					throw new HttpError(422, 'retention must keep at least one snapshot and no negative counts'); // prettier-ignore
				if (body.schedule !== undefined) target.schedule = body.schedule;
				if ('quiet_window' in body) target.quiet_window = body.quiet_window ?? null;
				target.retention = retention;
				if (body.enabled !== undefined) target.enabled = body.enabled;
				return ok(targetOut(target));
			}
		],
		['POST', /^\/api\/backups\/(\d+)\/run$/, (ctx) => ok(queueRun(findBackup(ctx), 'backup'), 202)],
		[
			'POST',
			/^\/api\/backups\/(\d+)\/restore-test$/,
			(ctx) => ok(queueRun(findBackup(ctx), 'restore_test'), 202)
		],
		[
			'GET',
			/^\/api\/backups\/(\d+)\/runs$/,
			(ctx) => {
				const target = findBackup(ctx);
				settle(target);
				const limit = Number(ctx.url.searchParams.get('limit') ?? 50);
				return ok(target.runs.slice(0, limit).map(({ ends_at: _e, ...r }) => r));
			}
		]
	];
}
