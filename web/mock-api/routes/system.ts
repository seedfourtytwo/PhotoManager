/** The system: health, what the library holds, and the job queue (admin). */
import { admin, HttpError, idParam, me, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

export function systemRoutes(h: Helpers): Route[] {
	return [
		['GET', /^\/api\/health$/, () => ok({ status: 'ok', version: 'mock' })],
		[
			'GET',
			/^\/api\/stats$/,
			(ctx) => {
				const counts = { queued: 0, waiting: 0, running: 0, done: 0, failed: 0 };
				for (const j of h.state().jobs)
					counts[j.status === 'queued' && j.run_after !== null ? 'waiting' : j.status]++;
				return ok({
					assets: h.visible(me(ctx)).length,
					sources: h.state().sources.length,
					jobs: counts,
					free_bytes: 412_000_000_000
				});
			}
		],
		[
			'GET',
			/^\/api\/jobs$/,
			(ctx) => {
				admin(ctx);
				const status = ctx.url.searchParams.get('status');
				return ok(
					h
						.state()
						.jobs.filter((j) =>
							status === 'waiting'
								? j.status === 'queued' && j.run_after !== null
								: !status || j.status === status
						)
						.map(({ run_at: _runAt, ...job }) => job)
				);
			}
		],
		[
			'POST',
			/^\/api\/jobs\/(\d+)\/retry$/,
			(ctx) => {
				admin(ctx);
				const job = h.state().jobs.find((j) => j.id === idParam(ctx) && j.status === 'failed');
				if (!job) throw new HttpError(404, 'No failed job with that id.');
				job.status = 'done';
				job.error = null;
				job.attempts++;
				return ok({ queued: true });
			}
		]
	];
}
