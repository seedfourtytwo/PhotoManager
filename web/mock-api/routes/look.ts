/** The look sheet (v1.5): each account's own mode, and the rest set by an admin. */
import { LookError, parseLook, readLook, type Look } from '../../src/lib/look/sheet.ts';
import { admin, HttpError, me, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

/** A sheet as the backend reads one: its refusal is a 422 with the sheet's own sentence. */
function sentLook(sheet: unknown): Look {
	try {
		return parseLook(sheet);
	} catch (error) {
		if (error instanceof LookError) throw new HttpError(422, error.message);
		throw error;
	}
}

export function lookRoutes(h: Helpers): Route[] {
	return [
		['GET', /^\/api\/me\/look$/, (ctx) => ok(readLook(me(ctx).look))],
		[
			'PUT',
			/^\/api\/me\/look$/,
			(ctx) => {
				const user = me(ctx);
				const sheet = ctx.body as Record<string, unknown> | null;
				if (typeof sheet !== 'object' || sheet === null || Object.keys(sheet).join() !== 'mode')
					throw new HttpError(
						422,
						'you can change only your mode: send {"mode": "dark"}, "light" or "system"; ' +
							'an admin sets the rest of your look'
					);
				user.look = { ...readLook(user.look), mode: sentLook(sheet).mode };
				return ok(user.look);
			}
		],
		[
			'GET',
			/^\/api\/admin\/accounts\/(\d+)\/look$/,
			(ctx) => (admin(ctx), ok(readLook(h.accountOf(ctx).look)))
		],
		[
			'PUT',
			/^\/api\/admin\/accounts\/(\d+)\/look$/,
			(ctx) => {
				admin(ctx);
				const user = h.accountOf(ctx);
				user.look = sentLook(ctx.body);
				return ok(user.look);
			}
		]
	];
}
