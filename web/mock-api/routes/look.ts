/** The look sheet (v1.5): each account's own mode and Home (v1.11), the rest set by an admin. */
import { LookError, OWN_FIELDS, parseLook, readLook, type Look } from '../../src/lib/look/sheet.ts';
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
				const fields = typeof sheet === 'object' && sheet !== null ? Object.keys(sheet) : [];
				if (
					Array.isArray(sheet) ||
					fields.length === 0 ||
					!fields.every((f) => (OWN_FIELDS as readonly string[]).includes(f))
				)
					throw new HttpError(
						422,
						'you can change only your mode and what your Home shows: send ' +
							'{"mode": "dark"}, "light" or "system", and or {"homeSections": [...]}; ' +
							'an admin sets the rest of your look'
					);
				const sent = sentLook(sheet);
				const own = Object.fromEntries(fields.map((f) => [f, sent[f as keyof Look]]));
				user.look = { ...readLook(user.look), ...own };
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
