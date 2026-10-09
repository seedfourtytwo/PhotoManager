/** Upload (v1.1): into the caller's private inbox source. */
import { HttpError, idParam, me, nowIso, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import { makeAsset, rng } from '../library.ts';
import type { MockUser } from '../types.ts';

/** The files of a multipart body: enough parsing for a mock (no nested parts). */
function multipartFiles(raw: Buffer, type: string) {
	const boundary = /boundary=("?)([^";]+)\1/.exec(type)?.[2];
	if (!boundary) throw new HttpError(400, 'Multipart upload without a boundary.');
	const files: { name: string; content: Buffer }[] = [];
	const marker = Buffer.from(`--${boundary}`);
	let start = raw.indexOf(marker);
	while (start !== -1) {
		const next = raw.indexOf(marker, start + marker.length);
		if (next === -1) break;
		const part = raw.subarray(start + marker.length + 2, next - 2);
		const split = part.indexOf('\r\n\r\n');
		const name = /filename="([^"]*)"/.exec(part.subarray(0, split).toString('utf8'))?.[1];
		if (split !== -1 && name) files.push({ name, content: part.subarray(split + 4) });
		start = next;
	}
	return files;
}

export function uploadRoutes(h: Helpers): Route[] {
	function inboxFor(user: MockUser) {
		let inbox = h.state().sources.find((s) => s.kind === 'inbox' && s.owner_id === user.id);
		if (!inbox) {
			inbox = {
				id: h.state().nextId.source++,
				label: `Uploads (${user.display_name})`,
				path: `inbox/${user.id}`,
				enabled: true,
				kind: 'inbox',
				owner_id: user.id,
				asset_count: 0
			};
			h.state().sources.push(inbox);
			h.state().access.set(inbox.id, {
				everyone: null,
				users: [{ user_id: user.id, level: 'edit' }]
			});
		}
		return inbox;
	}

	return [
		[
			'POST',
			/^\/api\/upload$/,
			(ctx) => {
				const user = me(ctx);
				if (user.role === 'guest')
					throw new HttpError(403, 'Guests can view and download, not upload.');
				const body = ctx.body as { multipart?: Buffer; type?: string } | undefined;
				if (!body?.multipart || !body.type)
					throw new HttpError(415, 'Send the photos as multipart/form-data.');
				const inbox = inboxFor(user);
				const month = nowIso().slice(0, 7);
				const files = multipartFiles(body.multipart, body.type).map(({ name, content }) => {
					const isPhoto =
						content.subarray(0, 3).equals(Buffer.from([0xff, 0xd8, 0xff])) ||
						content.subarray(0, 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47]));
					if (!isPhoto)
						return { name, outcome: 'rejected', stored_as: null, content_hash: null,
							asset_id: null, reason: 'not a photo' }; // prettier-ignore
					const asset = makeAsset(
						h.state().nextId.asset++,
						new Date(),
						null,
						'phone',
						rng(content.length)
					);
					asset.sources = [{ source_id: inbox.id, relative_path: `${month}/${name}` }];
					h.state().assets.push(asset);
					return { name, outcome: 'stored', stored_as: `${month}/${name}`,
						content_hash: null, asset_id: null, reason: null }; // prettier-ignore
				});
				const job = { id: h.state().nextId.job++, kind: 'import', payload: { source_id: inbox.id },
					status: 'done' as const, attempts: 1, error: null, run_after: null, run_at: 0 }; // prettier-ignore
				h.state().jobs.push(job);
				return ok({ files, import_job_id: job.id });
			}
		],
		// the import an upload of the caller queued; any other job is "not found"
		[
			'GET',
			/^\/api\/upload\/jobs\/(\d+)$/,
			(ctx) => {
				const user = me(ctx);
				if (user.role === 'guest')
					throw new HttpError(403, 'Guests can view and download, not upload.');
				const job = h.state().jobs.find((j) => j.id === idParam(ctx));
				const source = h.state().sources.find((s) => s.id === Number(job?.payload.source_id));
				const mine = source?.kind === 'inbox' && source.owner_id === user.id;
				if (!job || job.kind !== 'import' || !mine)
					throw new HttpError(404, 'No import of an upload of yours with that id.');
				return ok({ id: job.id, status: job.status, run_after: job.run_after });
			}
		]
	];
}
