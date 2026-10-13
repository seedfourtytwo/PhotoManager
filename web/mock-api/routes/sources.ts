/** Sources (folders the library imports from): adding, checking, scanning, who may see them. */
import type { Access, Source, SourcePatch } from '../../src/lib/api/types.ts';
import { live } from '../access.ts';
import { admin, HttpError, idParam, me, ok, requireFields, type Route } from '../http.ts';
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
			path: isAdmin ? s.path : null,
			problem: s.path.includes('gone') ? 'folder not found' : null,
			asset_count: h
				.state()
				.assets.filter((a) => live(a) && a.sources.some((o) => o.source_id === s.id)).length,
			recheck,
			next_check_at: next === null ? null : new Date(next).toISOString()
		};
	}

	return [
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
				if (!h.state().sources.some((s) => s.id === idParam(ctx)))
					throw new HttpError(404, 'Source not found.');
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
