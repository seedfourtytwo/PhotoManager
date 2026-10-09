/** Small HTTP vocabulary shared by the mock's route tables. */
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { MockUser } from './types.ts';

export class HttpError extends Error {
	readonly status: number;
	constructor(status: number, detail: string) {
		super(detail);
		this.status = status;
	}
}

export type Ctx = {
	req: IncomingMessage;
	res: ServerResponse;
	url: URL;
	params: string[];
	body: unknown;
	user: MockUser | null;
};
export type Result =
	| { status: number; json?: unknown; headers?: Record<string, string> }
	| { status: number; raw: Buffer | string; type: string; headers?: Record<string, string> };
export type Handler = (ctx: Ctx) => Result | Promise<Result>;
export type Route = [string, RegExp, Handler];

export const ok = (json: unknown, status = 200): Result => ({ status, json });
export const noContent: Result = { status: 204 };
export const nowIso = () => new Date().toISOString().slice(0, 19);
export const me = (ctx: Ctx) => ctx.user!;
export const idParam = (ctx: Ctx, i = 0) => Number(ctx.params[i]);

export function requireFields<T extends object>(body: unknown, fields: (keyof T)[]): T {
	if (!body || typeof body !== 'object') throw new HttpError(422, 'Expected a JSON body.');
	for (const f of fields)
		if (!(f in body)) throw new HttpError(422, `Missing field: ${String(f)}.`);
	return body as T;
}

export const admin = (ctx: Ctx) => {
	if (ctx.user?.role !== 'admin') throw new HttpError(403, 'Only an admin can do that.');
	return ctx.user;
};
