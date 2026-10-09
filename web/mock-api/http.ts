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

/** A body's list of photo ids, or a 422. */
export const ids = (body: unknown, key = 'ids'): number[] => {
	const value = (body as Record<string, unknown> | null)?.[key];
	if (!Array.isArray(value) || !value.every((v) => Number.isInteger(v)))
		throw new HttpError(422, `${key} must be a list of photo ids.`);
	return value as number[];
};

export async function readBody(req: IncomingMessage): Promise<unknown> {
	const chunks: Buffer[] = [];
	for await (const chunk of req) chunks.push(chunk as Buffer);
	const type = req.headers['content-type'] ?? '';
	if (type.startsWith('multipart/form-data')) return { multipart: Buffer.concat(chunks), type };
	const text = Buffer.concat(chunks).toString('utf8');
	if (!text) return undefined;
	if (type.includes('application/x-www-form-urlencoded'))
		return Object.fromEntries(new URLSearchParams(text));
	try {
		return JSON.parse(text);
	} catch {
		throw new HttpError(400, 'The request body is not valid JSON.');
	}
}

export function send(res: ServerResponse, result: Result) {
	const headers: Record<string, string> = { 'cache-control': 'no-store', ...result.headers };
	if ('raw' in result) {
		res.writeHead(result.status, { ...headers, 'content-type': result.type });
		res.end(result.raw);
	} else if (result.json === undefined) {
		res.writeHead(result.status, headers);
		res.end();
	} else {
		res.writeHead(result.status, { ...headers, 'content-type': 'application/json' });
		res.end(JSON.stringify(result.json));
	}
}
