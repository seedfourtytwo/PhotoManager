/** Remote (rclone) sources, admin. */
import { admin, HttpError, idParam, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

export function remoteSourceRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/remote-sources\/remotes$/,
			(ctx) => (admin(ctx), ok({ remotes: h.state().remotes }))
		],
		[
			'POST',
			/^\/api\/remote-sources$/,
			(ctx) => {
				const user = admin(ctx);
				const body = requireFields<{ label: string; remote: string; path?: string }>(ctx.body, ['label', 'remote']); // prettier-ignore
				if (!h.state().remotes.includes(body.remote))
					throw new HttpError(422, `rclone has no remote named '${body.remote}'`);
				if ((body.path ?? '').includes('..'))
					throw new HttpError(422, 'the path may not contain ..');
				const state = h.state();
				const source = {
					id: state.nextId.source++,
					label: body.label,
					path: `${body.remote}:${body.path ?? ''}`,
					enabled: true,
					kind: 'rclone',
					owner_id: user.id,
					asset_count: 0
				};
				state.sources.push(source);
				state.access.set(source.id, { everyone: 'download', users: [] });
				state.remoteSources.set(source.id, { remote: body.remote, path: body.path ?? '' });
				return ok({ id: source.id, label: body.label, remote: body.remote, path: body.path ?? '' }, 201); // prettier-ignore
			}
		],
		[
			'POST',
			/^\/api\/remote-sources\/(\d+)\/pull$/,
			(ctx) => {
				admin(ctx);
				if (!h.state().remoteSources.has(idParam(ctx)))
					throw new HttpError(404, 'no remote source with that id');
				return ok(h.queueScan(idParam(ctx)), 202);
			}
		]
	];
}
