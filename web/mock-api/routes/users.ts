/** Users: the admin's list of accounts, and the names anyone may share an album with. */
import type { Role } from '../../src/lib/api/types.ts';
import { checkPin, forgiveWrongPins } from '../accounts.ts';
import { noWrongPins } from '../data.ts';
import {
	admin,
	HttpError,
	idParam,
	me,
	noContent,
	ok,
	requireFields,
	type Route
} from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockUser } from '../types.ts';

export function userRoutes(h: Helpers): Route[] {
	return [
		['GET', /^\/api\/users$/, (ctx) => (admin(ctx), ok(h.state().users.map(h.managedUser)))],
		[
			'GET',
			/^\/api\/users\/directory$/,
			(ctx) => {
				const user = me(ctx);
				if (user.role === 'guest') throw new HttpError(403, "Guests can't share albums.");
				const shown = h.state().users.filter((u) => user.role === 'admin' || !u.disabled);
				return ok(shown.map((u) => ({ id: u.id, display_name: u.display_name })));
			}
		],
		[
			'POST',
			/^\/api\/users$/,
			(ctx) => {
				admin(ctx);
				const body = requireFields<{
					username: string;
					display_name: string;
					pin: string;
					role: Role;
				}>(ctx.body, ['username', 'display_name', 'pin', 'role']);
				checkPin(body.pin);
				if (h.state().users.some((u) => u.username === body.username))
					throw new HttpError(409, 'That user name is taken.');
				const user: MockUser = {
					...body,
					id: h.state().nextId.user++,
					disabled: false,
					...noWrongPins()
				};
				h.state().users.push(user);
				return ok(h.managedUser(user), 201);
			}
		],
		[
			'PATCH',
			/^\/api\/users\/(\d+)$/,
			(ctx) => {
				admin(ctx);
				const user = h.state().users.find((u) => u.id === idParam(ctx));
				if (!user) throw new HttpError(404, 'User not found.');
				const body = (ctx.body ?? {}) as Partial<MockUser>;
				const admins = h.state().users.filter((u) => u.role === 'admin' && !u.disabled);
				const losesAdmin =
					user.role === 'admin' && ((body.role && body.role !== 'admin') || body.disabled === true);
				if (losesAdmin && admins.length <= 1)
					throw new HttpError(409, 'The library needs at least one admin.');
				if (body.pin !== undefined) checkPin(body.pin);
				Object.assign(
					user,
					Object.fromEntries(
						Object.entries(body).filter(([k]) =>
							['display_name', 'role', 'disabled', 'pin'].includes(k)
						)
					)
				);
				if (body.pin !== undefined) forgiveWrongPins(user); // a new PIN lifts the lock
				if (user.disabled)
					for (const [t, id] of h.state().sessions)
						if (id === user.id) h.state().sessions.delete(t);
				return ok(h.managedUser(user));
			}
		],
		[
			'POST',
			/^\/api\/users\/(\d+)\/unlock$/,
			(ctx) => {
				admin(ctx);
				const user = h.state().users.find((u) => u.id === idParam(ctx));
				if (!user) throw new HttpError(404, 'User not found.');
				forgiveWrongPins(user);
				return noContent;
			}
		]
	];
}
