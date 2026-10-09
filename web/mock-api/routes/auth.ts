/** First-run setup and signing in: the session cookie, and PINs. */
import { checkPin, forgiveWrongPins, publicUser } from '../accounts.ts';
import { noWrongPins } from '../data.ts';
import { HttpError, me, noContent, ok, requireFields, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockUser } from '../types.ts';

export function authRoutes(h: Helpers): Route[] {
	return [
		['GET', /^\/api\/setup$/, () => ok({ needs_admin: h.state().users.length === 0 })],
		[
			'POST',
			/^\/api\/setup$/,
			(ctx) => {
				if (h.state().users.length > 0)
					throw new HttpError(409, 'The library already has an admin.');
				const body = requireFields<{ username: string; display_name: string; pin: string }>(
					ctx.body,
					['username', 'display_name', 'pin']
				);
				checkPin(body.pin);
				const user: MockUser = {
					id: h.state().nextId.user++,
					username: body.username,
					display_name: body.display_name,
					role: 'admin',
					disabled: false,
					pin: body.pin,
					...noWrongPins()
				};
				h.state().users.push(user);
				return { status: 201, json: publicUser(user), headers: h.startSession(user) };
			}
		],
		[
			'GET',
			/^\/api\/auth\/accounts$/,
			() =>
				ok(
					h
						.state()
						.users.filter((u) => !u.disabled)
						.map((u) => ({ username: u.username, display_name: u.display_name }))
				)
		],
		[
			'POST',
			/^\/api\/auth\/login$/,
			(ctx) => {
				const body = requireFields<{ username: string; pin: string }>(ctx.body, [
					'username',
					'pin'
				]);
				const name = body.username.toLowerCase(); // user names ignore case
				const user = h.state().users.find((u) => u.username.toLowerCase() === name);
				// a name nobody has is refused at once: nothing to count, nothing to lock
				if (!user || !h.tryPin(user, body.pin) || user.disabled)
					throw new HttpError(401, 'Wrong PIN.');
				forgiveWrongPins(user);
				return { status: 200, json: publicUser(user), headers: h.startSession(user) };
			}
		],
		[
			'POST',
			/^\/api\/auth\/logout$/,
			(ctx) => {
				const token = /pa_session=([^;]+)/.exec(ctx.req.headers.cookie ?? '')?.[1];
				if (token) h.state().sessions.delete(token);
				return {
					status: 204,
					headers: { 'set-cookie': 'pa_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' }
				};
			}
		],
		['GET', /^\/api\/auth\/me$/, (ctx) => ok(publicUser(me(ctx)))],
		[
			'POST',
			/^\/api\/auth\/pin$/,
			(ctx) => {
				const body = requireFields<{ current_pin: string; new_pin: string }>(ctx.body, [
					'current_pin',
					'new_pin'
				]);
				if (!h.tryPin(me(ctx), body.current_pin))
					throw new HttpError(400, 'The current PIN is wrong.');
				forgiveWrongPins(me(ctx));
				checkPin(body.new_pin);
				me(ctx).pin = body.new_pin;
				return noContent;
			}
		]
	];
}
