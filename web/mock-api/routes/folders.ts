/** The folder picker (admin): the machine's folders, and making a new one. */
import { admin, HttpError, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

export function folderRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/folders$/,
			(ctx) => (admin(ctx), ok(h.listFolders(ctx.url.searchParams.get('path') ?? undefined)))
		],
		[
			'POST',
			/^\/api\/folders$/,
			(ctx) => {
				admin(ctx);
				const { path } = requireFields<{ path: string }>(ctx.body, ['path']);
				if (!path.startsWith('/'))
					throw new HttpError(422, 'give the full path of the folder, starting with /');
				if (!path.includes('missing') || h.state().createdFolders.has(path))
					throw new HttpError(422, `${path} already exists`);
				h.state().createdFolders.add(path);
				return ok(h.listFolders(path), 201);
			}
		]
	];
}
