/** Devices: the tokens a phone or a desktop app signs in with, each user's own. */
import { randomBytes } from 'node:crypto';
import {
	HttpError,
	idParam,
	me,
	noContent,
	nowIso,
	ok,
	requireFields,
	type Route
} from '../http.ts';
import type { Helpers } from '../helpers.ts';
import type { MockState } from '../types.ts';

const deviceOut = ({ user_id: _u, token: _t, ...d }: MockState['devices'][number]) => d;

export function deviceRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/devices$/,
			(ctx) =>
				ok(
					h
						.state()
						.devices.filter((d) => d.user_id === me(ctx).id)
						.map(deviceOut)
				)
		],
		[
			'POST',
			/^\/api\/devices$/,
			(ctx) => {
				const body = requireFields<{ name: string; platform?: string }>(ctx.body, ['name']);
				if (!body.name.trim()) throw new HttpError(422, 'give the device a name');
				const platform = body.platform ?? 'other';
				if (!['ios', 'android', 'desktop', 'other'].includes(platform))
					throw new HttpError(422, `unknown platform ${platform}`);
				const device = {
					id: h.state().devices.length + 1,
					user_id: me(ctx).id,
					token: `pa_dev_${randomBytes(24).toString('base64url')}`,
					name: body.name.trim(),
					platform: platform as 'ios',
					created_at: nowIso(),
					last_used_at: null,
					revoked: false
				};
				h.state().devices.push(device);
				return ok({ device: deviceOut(device), token: device.token }, 201);
			}
		],
		[
			'DELETE',
			/^\/api\/devices\/(\d+)$/,
			(ctx) => {
				const device = h.state().devices.find((d) => d.id === idParam(ctx) && d.user_id === me(ctx).id); // prettier-ignore
				if (!device) throw new HttpError(404, 'device not found');
				device.revoked = true;
				return noContent;
			}
		]
	];
}
