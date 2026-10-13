/**
 * Send to a device: a one-time link to chosen photos (contract v1.6). The sender's routes
 * need a session; `look` and `collect` take the link's token instead. Switched off (the
 * product's default) every route here is a 404. Kept simple: no limit on wrong tokens.
 */
import { randomBytes } from 'node:crypto';
import type {
	Handover,
	HandoverIn,
	HandoverOptions,
	LinkAddress
} from '../../src/lib/api/types.ts';
import { live, rank } from '../access.ts';
import type { Helpers } from '../helpers.ts';
import {
	HttpError,
	idParam,
	ids,
	me,
	noContent,
	ok,
	requireFields,
	type Ctx,
	type Result,
	type Route
} from '../http.ts';
import { renderAsset } from '../images.ts';
import type { MockAsset, MockHandover, MockUser } from '../types.ts';
import { zip } from '../zip.ts';

const MAX_PHOTOS = 100;
const MAX_BYTES = 1_000_000_000;
const GONE =
	'this link does not work any more: it was used, ran out or was cancelled; ask for a new one';
const NO_ADDRESS =
	'other devices cannot open the address you are using; an admin can set one they can ' +
	'(PA_SEND_TO_DEVICE_ADDRESS)';
const SEALED = { 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' };

/** The two routes a device without a session may call. */
export const TOKEN_ROUTES = ['/api/handovers/look', '/api/handovers/collect'];

export function handoverRoutes(h: Helpers): Route[] {
	const rules = () => h.state().sendToDevice;
	const iso = (ms: number) => new Date(ms).toISOString();

	function on() {
		if (!rules().enabled) throw new HttpError(404, 'Not Found');
	}
	function sender(ctx: Ctx): MockUser {
		on();
		if (me(ctx).role === 'guest')
			throw new HttpError(403, 'guests can view and download, not change anything');
		return me(ctx);
	}

	/**
	 * Where a link may point: the address of the web app in front of the mock counts as the
	 * home one. The dev server's proxy puts the mock's own name in Host, so the page's
	 * address is read from Referer (or Origin) when there is one.
	 */
	function addresses(ctx: Ctx): LinkAddress[] {
		const page = ctx.req.headers.referer ?? ctx.req.headers.origin;
		const host = page ? new URL(page).host : (ctx.req.headers.host ?? '127.0.0.1');
		const found: LinkAddress[] = [];
		if (rules().https) found.push({ via: 'here', origin: `https://${host}`, encrypted: true });
		if (rules().home) found.push({ via: 'home', origin: `http://${host}`, encrypted: false });
		return found;
	}

	function stateOf(x: MockHandover): Handover['state'] {
		if (x.cancelled) return 'cancelled';
		if (x.redeemed_at !== null) return 'redeemed';
		return h.now() >= x.expires ? 'expired' : 'waiting';
	}

	function out(x: MockHandover): Handover {
		const by = h.state().users.find((u) => u.id === x.user_id);
		return {
			id: x.id,
			state: stateOf(x),
			count: x.ids.length,
			bytes: x.bytes,
			created_at: iso(x.created),
			expires_at: iso(x.expires),
			encrypted: x.encrypted,
			details_removed: x.details_removed,
			sent_by: { id: x.user_id, display_name: by?.display_name ?? '?' },
			redeemed_at: x.redeemed_at === null ? null : iso(x.redeemed_at),
			redeemed_from: x.redeemed_from,
			redeemed_agent: x.redeemed_agent
		};
	}

	function mine(ctx: Ctx): MockHandover {
		const user = sender(ctx);
		const found = h.state().handovers.find((x) => x.id === idParam(ctx));
		if (!found || (user.role !== 'admin' && found.user_id !== user.id))
			throw new HttpError(404, 'no such link');
		return found;
	}

	/** The photos the sender may send now: seen, live, and at download level. */
	function sendable(user: MockUser, wanted: number[]): MockAsset[] {
		return wanted
			.map((id) => h.state().assets.find((a) => a.id === id && live(a)))
			.filter((a): a is MockAsset => !!a && rank(h.assetLevel(user, a)) >= rank('download'));
	}

	function create(ctx: Ctx): Result {
		const user = sender(ctx);
		const body = requireFields<HandoverIn>(ctx.body, ['ids', 'via', 'remove_details']);
		const address = addresses(ctx).find((a) => a.via === body.via);
		if (!address) throw new HttpError(422, NO_ADDRESS);
		const wanted = [...new Set(ids(body))];
		if (wanted.length < 1) throw new HttpError(422, 'choose at least one photo to send');
		const seen = wanted.map((id) => h.state().assets.find((a) => a.id === id && live(a)));
		if (seen.some((a) => !a || h.assetLevel(user, a) === null))
			throw new HttpError(404, 'some of these photos were not found');
		const allowed = sendable(user, wanted);
		if (allowed.length !== wanted.length)
			throw new HttpError(403, "you need 'download' access for this");
		if (wanted.length > MAX_PHOTOS)
			throw new HttpError(
				422,
				`a link carries at most ${MAX_PHOTOS} photos; you chose ${wanted.length}`
			);
		const bytes = allowed.reduce((sum, a) => sum + a.byte_size, 0);
		if (bytes > MAX_BYTES) throw new HttpError(422, 'these photos are too big for one link');
		if (!address.encrypted && !rules().unencrypted)
			throw new HttpError(
				403,
				'sending without encryption is switched off here: open the library at its https ' +
					'address and send from there'
			);
		if (!address.encrypted && !body.unencrypted_ok)
			throw new HttpError(
				409,
				'this link is not encrypted: anyone on the same network could see the photos ' +
					'while they travel; confirm to send anyway'
			);
		const made: MockHandover = {
			id: h.state().handovers.length + 1,
			token: randomBytes(32).toString('base64url'),
			user_id: user.id,
			ids: wanted,
			bytes,
			created: h.now(),
			expires: h.now() + rules().seconds * 1000,
			encrypted: address.encrypted,
			details_removed: body.remove_details,
			redeemed_at: null,
			redeemed_from: null,
			redeemed_agent: null,
			cancelled: false
		};
		h.state().handovers.push(made);
		return ok({ ...out(made), url: `${address.origin}/receive.html#${made.token}` }, 201);
	}

	/** The waiting hand-over a token opens, and what its sender may still send; else one 404. */
	function waiting(ctx: Ctx): { handover: MockHandover; photos: MockAsset[]; by: MockUser } {
		on();
		const token = (ctx.body as { token?: unknown } | undefined)?.token;
		const handover = h.state().handovers.find((x) => x.token === token);
		const by = h.state().users.find((u) => u.id === handover?.user_id);
		if (!handover || stateOf(handover) !== 'waiting' || !by || by.disabled)
			throw new HttpError(404, GONE);
		const photos = sendable(by, handover.ids);
		if (!photos.length) throw new HttpError(404, GONE);
		return { handover, photos, by };
	}

	function collect(ctx: Ctx): Result {
		const { handover, photos } = waiting(ctx);
		handover.redeemed_at = h.now();
		handover.redeemed_from = ctx.req.socket.remoteAddress ?? null;
		handover.redeemed_agent = (ctx.req.headers['user-agent'] ?? '').slice(0, 200) || null;
		const names = photos.map((a, i) => {
			const own = (a.sources[0].relative_path.split('/').pop() ?? `${a.id}`).replace(/\.\w+$/, '');
			const neutral = i === 0 ? 'photo' : `photo_${i + 1}`;
			return `${handover.details_removed ? neutral : own}.svg`;
		});
		const skipped = { 'x-skipped': String(handover.ids.length - photos.length) };
		if (photos.length === 1)
			return {
				status: 200,
				raw: renderAsset(photos[0]),
				type: 'image/svg+xml',
				headers: {
					...SEALED,
					...skipped,
					'content-disposition': `attachment; filename="${names[0]}"`
				}
			};
		const archive = zip(
			photos.map((a, i) => ({ name: names[i], data: Buffer.from(renderAsset(a)) }))
		);
		return {
			status: 200,
			raw: archive,
			type: 'application/zip',
			headers: {
				...SEALED,
				...skipped,
				'content-disposition': `attachment; filename="photos-${photos.length}.zip"`
			}
		};
	}

	return [
		[
			'GET',
			/^\/api\/handovers\/options$/,
			(ctx): Result => {
				sender(ctx);
				const options: HandoverOptions = {
					addresses: addresses(ctx),
					unencrypted_allowed: rules().unencrypted,
					remove_details: true,
					minutes: Math.max(1, Math.round(rules().seconds / 60)),
					max_photos: MAX_PHOTOS,
					max_bytes: MAX_BYTES
				};
				return ok(options);
			}
		],
		['POST', /^\/api\/handovers$/, create],
		[
			'GET',
			/^\/api\/handovers$/,
			(ctx) => {
				const user = sender(ctx);
				const shown = h
					.state()
					.handovers.filter((x) => user.role === 'admin' || x.user_id === user.id);
				return ok(shown.map(out).reverse());
			}
		],
		['GET', /^\/api\/handovers\/(\d+)$/, (ctx) => ok(out(mine(ctx)))],
		[
			'DELETE',
			/^\/api\/handovers\/(\d+)$/,
			(ctx) => {
				const found = mine(ctx);
				const why = {
					redeemed: 'these photos were already downloaded',
					expired: 'this link has already run out',
					cancelled: 'this link was already cancelled',
					waiting: ''
				}[stateOf(found)];
				if (why) throw new HttpError(409, why);
				found.cancelled = true;
				return noContent;
			}
		],
		[
			'POST',
			/^\/api\/handovers\/look$/,
			(ctx): Result => {
				const { handover, photos, by } = waiting(ctx);
				return {
					status: 200,
					json: {
						count: photos.length,
						sent_by: by.display_name,
						expires_at: iso(handover.expires),
						encrypted: handover.encrypted,
						details_removed: handover.details_removed
					},
					headers: SEALED
				};
			}
		],
		['POST', /^\/api\/handovers\/collect$/, collect]
	];
}
