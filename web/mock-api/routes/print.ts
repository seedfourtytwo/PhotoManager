/** Printing an album: the options, the page plan, a page preview and the PDF. */
import type { PrintPlan, PrintRequest } from '../../src/lib/api/types.ts';
import { HttpError, me, ok, type Ctx, type Route } from '../http.ts';
import type { Helpers } from '../helpers.ts';
import { renderAsset } from '../images.ts';
import type { MockAlbum, MockAsset } from '../types.ts';

const TRIMS = [
	{ id: 'a4-landscape', label: 'A4 landscape', width_mm: 297, height_mm: 210 },
	{ id: 'a4-portrait', label: 'A4 portrait', width_mm: 210, height_mm: 297 },
	{ id: 'square-20', label: 'Square 20 cm', width_mm: 200, height_mm: 200 }
];
const THEMES = [
	{ id: 'quiet', label: 'Quiet', paper: '#fbfaf7', ink: '#1a1a1a', font: 'Libertinus Serif' },
	{ id: 'warm', label: 'Warm', paper: '#f4ede1', ink: '#3b2f25', font: 'New Computer Modern' },
	{ id: 'night', label: 'Night', paper: '#151515', ink: '#ececec', font: 'Libertinus Serif' }
];
const LAYOUTS = [
	{ id: 'full-bleed', label: 'Full bleed', capacity: 1 },
	{ id: 'two-side', label: 'Two side by side', capacity: 2 },
	{ id: 'four-grid', label: 'Four in a grid', capacity: 4 }
];

export function printRoutes(h: Helpers): Route[] {
	function printable(ctx: Ctx) {
		const album = h.findAlbum(ctx);
		const user = me(ctx);
		const items = album.items
			.map((id) => h.state().assets.find((a) => a.id === id && a.trashed_at === null))
			.filter((a): a is MockAsset => !!a && h.assetLevel(user, a) !== null);
		if (items.some((a) => h.assetLevel(user, a) === 'view'))
			throw new HttpError(403, "printing needs 'download' access to every photo");
		if (items.length === 0) throw new HttpError(422, 'the album is empty');
		return { album, items };
	}

	function readPrint(body: unknown): PrintRequest {
		const req = { trim: 'a4-landscape', theme: 'quiet', cover: true, crop_marks: false, ...(body as object) };
		if (!TRIMS.some((t) => t.id === req.trim)) throw new HttpError(422, `unknown trim size ${req.trim}`);
		if (!THEMES.some((t) => t.id === req.theme)) throw new HttpError(422, `unknown theme ${req.theme}`);
		return req;
	} // prettier-ignore

	function plan(items: MockAsset[], req: PrintRequest): PrintPlan {
		const trim = TRIMS.find((t) => t.id === req.trim)!;
		const pages: PrintPlan['pages'] = [];
		const cycle = ['full-bleed', 'four-grid', 'two-side'];
		for (let i = 0, n = 0; i < items.length; n++) {
			const layout = LAYOUTS.find((l) => l.id === cycle[n % cycle.length])!;
			pages.push({ layout_id: layout.id, photos: items.slice(i, i + layout.capacity).map((a) => a.id), text: '' }); // prettier-ignore
			i += layout.capacity;
		}
		const issues: PrintPlan['issues'] = [];
		for (const page of pages) {
			const share = LAYOUTS.find((l) => l.id === page.layout_id)!.capacity > 2 ? 2 : 1;
			const inches = Math.min(trim.width_mm, trim.height_mm) / 25.4 / share;
			for (const id of page.photos) {
				const a = items.find((x) => x.id === id)!;
				const ppi = Math.round((Math.min(a.width, a.height) / inches) * 10) / 10;
				if (ppi < 200) issues.push({ asset_id: id, ppi, level: ppi < 150 ? 'block' : 'warn' });
			}
		}
		return { pages, issues, page_count: pages.length + (req.cover ? 1 : 0) };
	}

	function pageSvg(album: MockAlbum, items: MockAsset[], req: PrintRequest, page: number) {
		const trim = TRIMS.find((t) => t.id === req.trim)!;
		const theme = THEMES.find((t) => t.id === req.theme)!;
		const planned = plan(items, req);
		const W = trim.width_mm;
		const H = trim.height_mm;
		const image = (a: MockAsset, x: number, y: number, w: number, hh: number) =>
			`<image x="${x}" y="${y}" width="${w}" height="${hh}" preserveAspectRatio="xMidYMid meet" href="data:image/svg+xml;base64,${Buffer.from(renderAsset(a)).toString('base64')}"/>`;
		let body: string;
		if (req.cover && page === 1) {
			body = `${image(items[0], W * 0.1, H * 0.08, W * 0.8, H * 0.62)}<text x="${W / 2}" y="${H * 0.84}" font-family="serif" font-size="${H * 0.06}" text-anchor="middle" fill="${theme.ink}">${album.title.replace(/[<&]/g, '')}</text>`;
		} else {
			const p = planned.pages[page - (req.cover ? 2 : 1)];
			if (!p) throw new HttpError(422, 'no such page in this album');
			const photos = p.photos.map((id) => items.find((a) => a.id === id)!);
			const m = p.layout_id === 'full-bleed' ? 0 : 12;
			const cols = photos.length > 1 ? 2 : 1;
			const rows = photos.length > 2 ? 2 : 1;
			const cw = (W - m * 2 - (cols - 1) * 4) / cols;
			const ch = (H - m * 2 - (rows - 1) * 4) / rows;
			body = photos
				.map((a, i) => image(a, m + (i % cols) * (cw + 4), m + Math.floor(i / cols) * (ch + 4), cw, ch))
				.join(''); // prettier-ignore
		}
		return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W * 3}" height="${H * 3}"><rect width="${W}" height="${H}" fill="${theme.paper}"/>${body}</svg>`;
	}

	return [
		[
			'GET',
			/^\/api\/print\/options$/,
			() => ok({ trims: TRIMS, themes: THEMES, layouts: LAYOUTS })
		],
		[
			'POST',
			/^\/api\/albums\/(\d+)\/print\/plan$/,
			(ctx) => {
				const { items } = printable(ctx);
				return ok(plan(items, readPrint(ctx.body)));
			}
		],
		[
			'GET',
			/^\/api\/albums\/(\d+)\/print\/preview$/,
			(ctx) => {
				const { album, items } = printable(ctx);
				const q = ctx.url.searchParams;
				const req = readPrint({
					trim: q.get('trim') ?? undefined,
					theme: q.get('theme') ?? undefined,
					cover: q.get('cover') !== 'false'
				});
				const page = Number(q.get('page'));
				if (!Number.isInteger(page) || page < 1) throw new HttpError(422, 'page must be 1 or more');
				// The real server renders a PNG; an SVG page is enough for the mock's <img>.
				return { status: 200, raw: pageSvg(album, items, req, page), type: 'image/svg+xml' };
			}
		],
		[
			'POST',
			/^\/api\/albums\/(\d+)\/print$/,
			(ctx) => {
				const { album, items } = printable(ctx);
				const req = readPrint(ctx.body);
				const { issues } = plan(items, req);
				const blocked = issues.filter((i) => i.level === 'block');
				if (blocked.length && !req.allow_low_resolution)
					return {
						status: 422,
						json: {
							detail: `${blocked.length} photo${blocked.length === 1 ? ' is' : 's are'} too small to print sharply at this size`,
							issues
						}
					};
				const name = `${album.title.replace(/[^\w\- ]+/g, '_').trim() || 'album'}.pdf`;
				return {
					status: 200,
					raw: `%PDF-1.4\n% mock album "${album.title}", ${items.length} photos\n%%EOF\n`,
					type: 'application/pdf',
					headers: {
						'content-disposition': `attachment; filename="${name}"`,
						'x-print-warnings': String(issues.length)
					}
				};
			}
		]
	];
}
