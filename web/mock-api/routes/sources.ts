/** Sources (folders the library imports from): adding, checking, scanning, who may see them. */
import type { Access, PhotosOnlyHere, Source, SourcePatch } from '../../src/lib/api/types.ts';
import { live } from '../access.ts';
import { admin, HttpError, idParam, me, nowIso, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockSource } from '../types.ts';

/** How long a source that checks itself waits between checks. */
const RECHECK_MS = { hourly: 3_600_000, daily: 86_400_000, weekly: 604_800_000 };

export function sourceRoutes(h: Helpers): Route[] {
	/** A source as the API sends it: counted, its path for admins only (v1.2), its next check. */
	function sourceOut(s: MockSource, isAdmin: boolean): Source {
		const recheck = s.recheck ?? 'off';
		const last = h.state().reports.find((r) => r.source_id === s.id); // newest first
		const next =
			recheck === 'off' || !s.enabled
				? null
				: last
					? Date.parse(last.started_at) + RECHECK_MS[recheck]
					: h.now(); // never checked: due at once
		return {
			...s,
			path: isAdmin && s.kind !== 'kept' ? s.path : null,
			problem: s.path.includes('gone') ? 'folder not found' : null,
			asset_count: h
				.state()
				.assets.filter((a) => live(a) && a.sources.some((o) => o.source_id === s.id)).length,
			recheck,
			next_check_at: next === null ? null : new Date(next).toISOString()
		};
	}

	function findSource(id: number): MockSource {
		const source = h.state().sources.find((s) => s.id === id);
		if (!source) throw new HttpError(404, 'source not found');
		return source;
	}

	/** Live photos in the folder, and those no other folder holds (as the server counts). */
	function holdings(id: number) {
		const photos = h
			.state()
			.assets.filter((a) => a.trashed_at === null && a.sources.some((o) => o.source_id === id));
		const onlyHere = photos.filter((a) => a.sources.every((o) => o.source_id === id));
		return { photos, onlyHere };
	}

	/** Stop watching (v1.6), with the server's statuses and sentences (app/stop_watching.py). */
	function removeSource(id: number, photos: PhotosOnlyHere) {
		const source = findSource(id);
		if (source.kind === 'inbox')
			throw new HttpError(422, 'an upload inbox belongs to its account and cannot be removed');
		const state = h.state();
		const itsCheck = (job: (typeof state.jobs)[number]) =>
			job.kind === 'import' && Number(job.payload.source_id) === id;
		if (state.jobs.some((job) => itsCheck(job) && job.status === 'running'))
			throw new HttpError(
				409,
				'this folder is being checked right now; try again when the check is done'
			);
		const { onlyHere } = holdings(id);
		state.jobs = state.jobs.filter((job) => !itsCheck(job));
		if (photos === 'keep' && source.kind !== 'kept') {
			// Detached: never checked again, its folder free, its access and photos as they were.
			Object.assign(source, { kind: 'kept', path: `kept:${id}`, enabled: false, recheck: 'off' });
			return { only_here: onlyHere.length, trashed: 0, detached: true };
		}
		if (photos === 'trash') for (const a of onlyHere) a.trashed_at = nowIso();
		for (const a of state.assets) a.sources = a.sources.filter((o) => o.source_id !== id);
		state.reports = state.reports.filter((r) => r.source_id !== id);
		state.access.delete(id);
		state.sources = state.sources.filter((s) => s !== source);
		const trashed = photos === 'trash' ? onlyHere.length : 0;
		return { only_here: onlyHere.length, trashed, detached: false };
	}

	/** A folder no longer watched cannot be checked or switched back on (as the server). */
	function requireWatchable(id: number): MockSource {
		const source = findSource(id);
		if (source.kind === 'kept')
			throw new HttpError(422, 'this folder is no longer watched; add it again to watch it');
		return source;
	}

	return [
		[
			'GET',
			/^\/api\/sources\/(\d+)\/removal$/,
			(ctx) => {
				admin(ctx);
				findSource(idParam(ctx));
				const { photos, onlyHere } = holdings(idParam(ctx));
				return ok({ photos: photos.length, only_here: onlyHere.length });
			}
		],
		[
			'DELETE',
			/^\/api\/sources\/(\d+)$/,
			(ctx) => {
				admin(ctx);
				const photos = ctx.url.searchParams.get('photos') ?? 'keep';
				if (photos !== 'keep' && photos !== 'trash')
					throw new HttpError(422, 'photos: keep or trash');
				return ok(removeSource(idParam(ctx), photos));
			}
		],
		[
			'GET',
			/^\/api\/sources$/,
			(ctx) => {
				// Like the server: an admin sees every source; anyone else their own and those
				// shared with them or with everyone, each with the photos they can see.
				const user = me(ctx);
				const shared = (id: number) => {
					const access = h.state().access.get(id);
					return !!access && (access.everyone !== null || access.users.some((u) => u.user_id === user.id)); // prettier-ignore
				};
				return ok(
					h
						.state()
						.sources.filter((s) => user.role === 'admin' || s.owner_id === user.id || shared(s.id))
						.map((s) => ({
							...sourceOut(s, user.role === 'admin'),
							asset_count: h
								.visible(user)
								.filter((a) => a.sources.some((o) => o.source_id === s.id)).length
						}))
				);
			}
		],
		[
			'POST',
			/^\/api\/sources$/,
			(ctx) => {
				const user = admin(ctx);
				const body = requireFields<{ label: string; path: string }>(ctx.body, ['label', 'path']);
				if (!body.label.trim()) throw new HttpError(422, 'Give the source a name.');
				// Statuses and sentences as in routes/sources.py.
				if (!body.path.startsWith('/'))
					throw new HttpError(422, 'give the full path of the folder, starting with /');
				if (body.path.includes('missing'))
					throw new HttpError(422, `folder not found on this machine: ${body.path}`);
				const same = (path: string) => path.replace(/\/+$/, '') === body.path.replace(/\/+$/, '');
				if (h.state().sources.some((s) => same(s.path)))
					throw new HttpError(409, `folder is already a source: ${body.path}`);
				const source = {
					id: h.state().nextId.source++,
					label: body.label,
					path: body.path,
					enabled: true,
					kind: 'folder',
					owner_id: user.id,
					asset_count: 0
				};
				h.state().sources.push(source);
				h.state().access.set(source.id, { everyone: 'download', users: [] });
				return ok(sourceOut(source, true), 201);
			}
		],
		[
			'PATCH',
			/^\/api\/sources\/(\d+)$/,
			(ctx) => {
				admin(ctx);
				const source = h.state().sources.find((s) => s.id === idParam(ctx));
				if (!source) throw new HttpError(404, 'Source not found.');
				const body = (ctx.body ?? {}) as SourcePatch;
				if (body.recheck !== undefined && !(body.recheck === 'off' || body.recheck in RECHECK_MS))
					throw new HttpError(422, 'Check automatically: off, hourly, daily or weekly.');
				if (body.enabled || (body.recheck !== undefined && body.recheck !== 'off'))
					requireWatchable(source.id);
				if (body.enabled !== undefined) source.enabled = body.enabled;
				if (body.label) source.label = body.label;
				if (body.recheck !== undefined) source.recheck = body.recheck;
				return ok(sourceOut(source, true));
			}
		],
		[
			'POST',
			/^\/api\/sources\/scan-all$/,
			(ctx) => (
				admin(ctx),
				ok(
					h
						.state()
						.sources.filter((s) => s.enabled)
						.map((s) => h.queueScan(s.id)),
					202
				)
			)
		],
		[
			'POST',
			/^\/api\/sources\/(\d+)\/scan$/,
			(ctx) => {
				admin(ctx);
				requireWatchable(idParam(ctx));
				return ok(h.queueScan(idParam(ctx)), 202);
			}
		],
		[
			'GET',
			/^\/api\/sources\/(\d+)\/access$/,
			(ctx) => {
				admin(ctx);
				const access = h.state().access.get(idParam(ctx));
				if (!access) throw new HttpError(404, 'Source not found.');
				return ok(access);
			}
		],
		[
			'PUT',
			/^\/api\/sources\/(\d+)\/access$/,
			(ctx) => {
				admin(ctx);
				if (!h.state().access.has(idParam(ctx))) throw new HttpError(404, 'Source not found.');
				const body = requireFields<Access>(ctx.body, ['everyone', 'users']);
				h.state().access.set(idParam(ctx), { everyone: body.everyone, users: body.users });
				return ok(h.state().access.get(idParam(ctx)));
			}
		]
	];
}
