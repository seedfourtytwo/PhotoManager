/** Import runs (admin): the list, and one run's report. */
import type { Outcome } from '../../src/lib/api/types.ts';
import { admin, HttpError, idParam, ok, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';

/** An import report lists what needs a look first (backend: domain/model.py REPORT_ORDER). */
const REPORT_ORDER: Outcome[] = ['failed', 'skipped', 'duplicate', 'already_known', 'imported'];

export function importRoutes(h: Helpers): Route[] {
	return [
		[
			'GET',
			/^\/api\/imports$/,
			(ctx) => {
				admin(ctx);
				const sourceId = ctx.url.searchParams.get('source_id');
				return ok(
					h
						.state()
						.reports.filter((r) => !sourceId || r.source_id === Number(sourceId))
						.map(({ items: _items, ...run }) => run)
				);
			}
		],
		[
			'GET',
			/^\/api\/imports\/(\d+)$/,
			(ctx) => {
				admin(ctx);
				const report = h.state().reports.find((r) => r.id === idParam(ctx));
				if (!report) throw new HttpError(404, 'Import run not found.');
				const outcome = ctx.url.searchParams.get('outcome');
				const limit = Number(ctx.url.searchParams.get('limit') ?? 500);
				const offset = Number(ctx.url.searchParams.get('offset') ?? 0);
				if (!Number.isInteger(limit) || limit < 1 || limit > 2000)
					throw new HttpError(422, 'limit must be between 1 and 2000.');
				if (!Number.isInteger(offset) || offset < 0)
					throw new HttpError(422, 'offset must not be negative.');
				// what needs a look first; within an outcome, in the order of the run
				const wanted = REPORT_ORDER.flatMap((o) =>
					!outcome || o === outcome ? report.items.filter((i) => i.outcome === o) : []
				);
				const items = wanted.slice(offset, offset + limit);
				const end = offset + items.length;
				return ok({
					id: report.id,
					source_id: report.source_id,
					status: report.status,
					message: report.message,
					summary: report.summary,
					items,
					total: wanted.length,
					limit,
					offset,
					next_offset: end < wanted.length ? end : null
				});
			}
		]
	];
}
