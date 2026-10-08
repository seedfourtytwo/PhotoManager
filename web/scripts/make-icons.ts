/**
 * Regenerates the PWA icons in static/: a sun inside two viewfinder corners, on the page colour.
 * No brand, no dependencies (PNG written with node:zlib).  node scripts/make-icons.ts
 */
import { writeFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';

const BG = [0x0d, 0x0f, 0x12];
const INK = [0xf1, 0xf2, 0xf4];
const SUN = [0xff, 0xb2, 0x4a];

function crc32(buf: Buffer): number {
	let c = 0xffffffff;
	for (const b of buf) {
		c ^= b;
		for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
	}
	return (c ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Buffer): Buffer {
	const len = Buffer.alloc(4);
	len.writeUInt32BE(data.length);
	const body = Buffer.concat([Buffer.from(type), data]);
	const crc = Buffer.alloc(4);
	crc.writeUInt32BE(crc32(body));
	return Buffer.concat([len, body, crc]);
}

/** `safe` shrinks the drawing for maskable icons (content inside the 80 % safe zone). */
function png(size: number, safe = 1): Buffer {
	const rows: Buffer[] = [];
	const c = size / 2;
	const r = size * 0.12 * safe; // the sun
	const reach = size * 0.27 * safe; // corner distance from the centre
	const arm = size * 0.17 * safe; // length of each corner stroke
	const thick = size * 0.045 * safe;
	const corner = (px: number, py: number, sign: 1 | -1) => {
		const x = (px - c) * sign + reach; // 0 at the corner's outer edge, growing inward
		const y = (py - c) * sign + reach;
		const inside = x >= 0 && y >= 0 && x <= arm && y <= arm;
		return inside && (x <= thick || y <= thick);
	};
	for (let y = 0; y < size; y++) {
		const row = Buffer.alloc(1 + size * 3);
		for (let x = 0; x < size; x++) {
			// 4× supersampling for smooth edges.
			let sun = 0;
			let ink = 0;
			for (let sy = 0; sy < 2; sy++)
				for (let sx = 0; sx < 2; sx++) {
					const px = x + 0.25 + sx * 0.5;
					const py = y + 0.25 + sy * 0.5;
					if (Math.hypot(px - c, py - c) <= r) sun++;
					else if (corner(px, py, 1) || corner(px, py, -1)) ink++;
				}
			const s = sun / 4;
			const k = ink / 4;
			for (let ch = 0; ch < 3; ch++)
				row[1 + x * 3 + ch] = Math.round(BG[ch] * (1 - s - k) + SUN[ch] * s + INK[ch] * k);
		}
		rows.push(row);
	}
	const ihdr = Buffer.alloc(13);
	ihdr.writeUInt32BE(size, 0);
	ihdr.writeUInt32BE(size, 4);
	ihdr[8] = 8;
	ihdr[9] = 2; // RGB
	return Buffer.concat([
		Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
		chunk('IHDR', ihdr),
		chunk('IDAT', deflateSync(Buffer.concat(rows))),
		chunk('IEND', Buffer.alloc(0))
	]);
}

// Browsers ask for /favicon.ico before reading the page; a PNG inside is accepted.
writeFileSync('static/favicon.ico', png(32));
writeFileSync('static/icon-192.png', png(192));
writeFileSync('static/icon-512.png', png(512));
writeFileSync('static/icon-maskable-512.png', png(512, 0.75));
writeFileSync(
	'src/lib/assets/favicon.svg',
	`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#0d0f12"/><circle cx="32" cy="32" r="7.5" fill="#ffb24a"/><path d="M15 26v-11h11M49 38v11h-11" fill="none" stroke="#f1f2f4" stroke-width="3" stroke-linecap="square"/></svg>\n`
);
