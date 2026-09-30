/**
 * Regenerates the PWA icons in static/: a sun over a horizon, ink on the dark background.
 * No brand, no dependencies (PNG written with node:zlib).  node scripts/make-icons.ts
 */
import { writeFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';

const BG = [0x11, 0x11, 0x11];
const INK = [0xed, 0xed, 0xed];

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
	const r = size * 0.14 * safe;
	const sunY = c - size * 0.04 * safe;
	const lineY = c + size * 0.16 * safe;
	const lineH = size * 0.03 * safe;
	const lineW = size * 0.32 * safe;
	for (let y = 0; y < size; y++) {
		const row = Buffer.alloc(1 + size * 3);
		for (let x = 0; x < size; x++) {
			// 4× supersampling for smooth edges.
			let hits = 0;
			for (let sy = 0; sy < 2; sy++)
				for (let sx = 0; sx < 2; sx++) {
					const px = x + 0.25 + sx * 0.5;
					const py = y + 0.25 + sy * 0.5;
					const sun = Math.hypot(px - c, py - sunY) <= r;
					const line = Math.abs(px - c) <= lineW && py >= lineY && py <= lineY + lineH;
					if (sun || line) hits++;
				}
			const t = hits / 4;
			for (let ch = 0; ch < 3; ch++)
				row[1 + x * 3 + ch] = Math.round(BG[ch] * (1 - t) + INK[ch] * t);
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
	`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#111"/><circle cx="32" cy="29.4" r="9" fill="#ededed"/><rect x="11.5" y="42.2" width="41" height="2" fill="#ededed"/></svg>\n`
);
