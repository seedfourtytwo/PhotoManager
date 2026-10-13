/** Proton Drive sources, admin (the mock machine is always signed in). */
import { admin, HttpError, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

export function protonRoutes(h: Helpers): Route[] {
	return [
		['GET', /^\/api\/proton$/, (ctx) => (admin(ctx), ok({ ready: true, problem: null }))],
		[
			'GET',
			/^\/api\/proton\/folders$/,
			(ctx) => {
				admin(ctx);
				const path = ctx.url.searchParams.get('path') ?? '';
				h.protonPlace(path, false);
				return ok({ path, folders: h.state().protonTree[path] ?? [] });
			}
		],
		[
			'POST',
			/^\/api\/proton\/folders$/,
			(ctx) => {
				admin(ctx);
				const { parent, name } = requireFields<{ parent: string; name: string }>(ctx.body, ['parent', 'name']); // prettier-ignore
				h.protonPlace(parent, false);
				const tree = h.state().protonTree;
				if (!name.trim() || /[/\\]/.test(name) || name.startsWith('-'))
					throw new HttpError(422, "a folder name can't contain / or \\ or line breaks");
				if (tree[parent].includes(name)) throw new HttpError(422, `'${name}' already exists there`);
				tree[parent] = [...tree[parent], name].sort((a, b) => a.localeCompare(b));
				tree[`${parent}/${name}`] = [];
				return ok({ path: `${parent}/${name}`, folders: [] }, 201);
			}
		],
		[
			'POST',
			/^\/api\/proton\/sources$/,
			(ctx) => {
				const user = admin(ctx);
				const body = requireFields<{ label: string; path: string }>(ctx.body, ['label', 'path']);
				h.protonPlace(body.path, true);
				const state = h.state();
				const source = {
					id: state.nextId.source++,
					label: body.label,
					path: body.path,
					enabled: true,
					kind: 'proton',
					owner_id: user.id,
					asset_count: 0
				};
				state.sources.push(source);
				state.access.set(source.id, { everyone: 'download', users: [] });
				state.remoteSources.set(source.id, { remote: 'proton', path: body.path });
				return ok({ id: source.id, label: body.label, path: body.path }, 201);
			}
		]
	];
}
