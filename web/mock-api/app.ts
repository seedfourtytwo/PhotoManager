/**
 * In-memory implementation of docs/contracts/api-v1.md for development and E2E tests.
 * Faithful to the contract (status codes, shapes, access rules) but deliberately simple.
 * Mock-only extras live under /__mock/ and are never used by the app itself.
 */
import type { IncomingMessage, ServerResponse } from 'node:http';
import { LOCK_AFTER_WRONG_PINS } from './accounts.ts';
import { makeState } from './data.ts';
import { createHelpers } from './helpers.ts';
import { HttpError, noContent, readBody, send, type Result, type Route } from './http.ts';
import { albumRoutes } from './routes/albums.ts';
import { suggestionRoutes } from './routes/suggestions.ts';
import { assetRoutes } from './routes/assets.ts';
import { authRoutes } from './routes/auth.ts';
import { backupRoutes } from './routes/backups.ts';
import { deviceSyncRoutes } from './routes/device-sync.ts';
import { deviceRoutes } from './routes/devices.ts';
import { downloadRoutes } from './routes/downloads.ts';
import { folderRoutes } from './routes/folders.ts';
import { homeRoutes } from './routes/home.ts';
import { importRoutes } from './routes/imports.ts';
import { lookRoutes } from './routes/look.ts';
import { peopleRoutes } from './routes/people.ts';
import { printRoutes } from './routes/print.ts';
import { protonRoutes } from './routes/proton.ts';
import { remoteSourceRoutes } from './routes/remote-sources.ts';
import { reviewRoutes } from './routes/review.ts';
import { searchRoutes } from './routes/search.ts';
import { sourceRoutes } from './routes/sources.ts';
import { systemRoutes } from './routes/system.ts';
import { trashRoutes } from './routes/trash.ts';
import { uploadRoutes } from './routes/upload.ts';
import { userRoutes } from './routes/users.ts';
import type { MockState } from './types.ts';

type MockOptions = { now?: () => number };

export function createMockApi(initial: MockState, options: MockOptions = {}) {
	let state = initial;
	const initialCount = initial.assets.length;
	const now = options.now ?? (() => Date.now());

	const h = createHelpers({ state: () => state, now });

	const routes: Route[] = [
		...systemRoutes(h),
		...authRoutes(h),
		...userRoutes(h),
		...lookRoutes(h),
		...uploadRoutes(h),
		...sourceRoutes(h),
		...importRoutes(h),
		...assetRoutes(h),
		...homeRoutes(h),
		...downloadRoutes(h),
		...albumRoutes(h),
		...suggestionRoutes(h),
		...reviewRoutes(h),
		...trashRoutes(h),
		...searchRoutes(h),
		...peopleRoutes(h),
		...printRoutes(h),
		...backupRoutes(h),
		...folderRoutes(h),
		...deviceRoutes(h),
		...deviceSyncRoutes(h),
		...remoteSourceRoutes(h),
		...protonRoutes(h)
	];

	/** `/__mock/reset` with `review`: one look-alike, two screenshots and a receipt wait. */
	function holdSome() {
		const [alike, original, ...rest] = state.assets;
		alike.held = { reason: 'lookalike', like: original.id };
		rest[0].held = rest[1].held = { reason: 'screenshot', like: null };
		rest[2].held = { reason: 'receipt', like: null };
	}

	const PUBLIC = new Set(['/api/health', '/api/setup', '/api/auth/accounts', '/api/auth/login']);

	async function mockRoute(url: URL, req: IncomingMessage): Promise<Result | null> {
		if (url.pathname === '/__mock/reset' && req.method === 'POST') {
			const body = ((await readBody(req)) ?? {}) as {
				users?: 'none' | 'seed';
				count?: number;
				models?: boolean;
				review?: boolean;
				/** A user name to start locked, as after 30 wrong PINs. */
				locked?: string;
			};
			state = makeState({
				users: body.users ?? 'seed',
				count: body.count ?? initialCount,
				now: now()
			});
			for (const user of state.users)
				if (user.username === body.locked)
					Object.assign(user, { failedPins: LOCK_AFTER_WRONG_PINS, locked: true });
			state.ml.installed = body.models ?? false;
			if (body.review) holdSome();
			return noContent;
		}
		return null;
	}

	async function handle(req: IncomingMessage, res: ServerResponse) {
		const url = new URL(req.url ?? '/', 'http://mock.local');
		try {
			const extra = await mockRoute(url, req);
			if (extra) return send(res, extra);
			h.advanceJobs();
			const route = routes.find(([m, re]) => m === req.method && re.test(url.pathname));
			if (!route) {
				const known = routes.some(([, re]) => re.test(url.pathname));
				throw new HttpError(known ? 405 : 404, known ? 'Method not allowed.' : 'Not found.');
			}
			const user = h.sessionUser(req);
			if (!user && !PUBLIC.has(url.pathname)) throw new HttpError(401, 'Please sign in.');
			const body = await readBody(req);
			const params = route[1].exec(url.pathname)!.slice(1);
			send(res, await route[2]({ req, res, url, params, body, user }));
		} catch (error) {
			const status = error instanceof HttpError ? error.status : 500;
			const detail = error instanceof Error ? error.message : 'Unexpected error.';
			send(res, { status, json: { detail } });
		}
	}

	return {
		handle,
		get state() {
			return state;
		}
	};
}
