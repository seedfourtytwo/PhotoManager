import { describe, expect, it } from 'vitest';
import table from '../../../docs/contracts/qr-cases.json?raw';
import {
	MAX_BYTES,
	QUIET_ZONE,
	capacity,
	checkBytes,
	encode,
	penalty,
	svgPath,
	versionFor
} from './qr';

/** Codes drawn by OpenCV's encoder, an implementation that shares nothing with ours. */
const CASES = (
	JSON.parse(table) as {
		cases: { text: string; version: number; mask: number; rows: string[] }[];
	}
).cases;

const rows = (modules: boolean[][]) =>
	modules.map((row) => row.map((dark) => (dark ? '1' : '0')).join(''));
const bytes = (text: string) => new TextEncoder().encode(text).length;

describe('the QR encoder', () => {
	it.each(CASES)(
		'draws "$text" square for square as the reference encoder does',
		({ text, version, mask, rows: expected }) => {
			const code = encode(text, { mask });
			expect(code.version).toBe(version);
			expect(code.size).toBe(expected.length);
			expect(rows(code.modules)).toEqual(expected);
		}
	);

	it('covers every version it offers, both block shapes and the version squares', () => {
		const versions = new Set(CASES.map((c) => c.version));
		expect([...versions].sort((a, b) => a - b)).toEqual([1, 2, 5, 6, 8, 10]);
		expect(new Set(CASES.map((c) => c.mask)).size).toBeGreaterThan(3);
	});

	it('picks the mask with the lowest penalty when none is forced', () => {
		for (const { text } of CASES) {
			const chosen = encode(text);
			const scores = [0, 1, 2, 3, 4, 5, 6, 7].map((mask) =>
				penalty(encode(text, { mask }).modules)
			);
			expect(scores[chosen.mask]).toBe(Math.min(...scores));
			expect(chosen.modules).toEqual(encode(text, { mask: chosen.mask }).modules);
		}
	});

	it('uses the smallest version that holds the text', () => {
		// level M, byte mode: the capacities the standard lists
		expect([1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(capacity)).toEqual([
			14, 26, 42, 62, 84, 106, 122, 152, 180, 213
		]);
		expect(versionFor(0)).toBe(1);
		expect(versionFor(14)).toBe(1);
		expect(versionFor(15)).toBe(2);
		expect(versionFor(180)).toBe(9);
		expect(versionFor(181)).toBe(10);
		expect(versionFor(MAX_BYTES)).toBe(10);
	});

	it('counts bytes, not characters', () => {
		expect(bytes('✓✓✓✓✓')).toBe(15);
		expect(encode('✓✓✓✓✓').version).toBe(2);
		expect(encode('abcde').version).toBe(1);
	});

	it('holds a link to the receiving page with room to spare', () => {
		const link = `https://a-long-machine-name.tail-scale-1234.ts.net/receive.html#${'x'.repeat(43)}`;
		expect(bytes(link)).toBeLessThan(120);
		expect(encode(link).version).toBeLessThanOrEqual(7);
	});

	it('refuses a text that does not fit, saying how long it may be', () => {
		expect(encode('x'.repeat(MAX_BYTES)).version).toBe(10);
		expect(() => encode('x'.repeat(MAX_BYTES + 1))).toThrow(/214 bytes, at most 213/);
	});

	it('computes the check bytes of the standard’s worked example', () => {
		// ISO/IEC 18004 Annex I ("01234567", version 1-M): 16 data bytes, 10 check bytes
		const data = [
			0x10, 0x20, 0x0c, 0x56, 0x61, 0x80, 0xec, 0x11, 0xec, 0x11, 0xec, 0x11, 0xec, 0x11, 0xec, 0x11
		];
		expect(checkBytes(data, 10)).toEqual([
			0xa5, 0x24, 0xd4, 0xc1, 0xed, 0x36, 0xc7, 0x87, 0x2c, 0x55
		]);
	});

	it('penalises long runs, blocks and an uneven share of dark squares', () => {
		const filled = (dark: boolean) => Array.from({ length: 6 }, () => new Array(6).fill(dark));
		// 12 lines of six alike (3 + 1 each), 25 blocks (3 each), 100 % dark (10 steps of 10)
		expect(penalty(filled(true))).toBe(12 * 4 + 25 * 3 + 100);
		const checkers = filled(false).map((row, y) => row.map((_, x) => (x + y) % 2 === 0));
		expect(penalty(checkers)).toBe(0);
	});
});

describe('the drawing', () => {
	it('is one path of runs inside a quiet zone of four squares', () => {
		const code = encode('a');
		const { path, viewBox } = svgPath(code);
		expect(viewBox).toBe(`0 0 ${21 + 2 * QUIET_ZONE} ${21 + 2 * QUIET_ZONE}`);
		// the top row of a finder pattern: seven dark squares starting at the quiet zone
		expect(path.startsWith('M4 4h7v1h-7z')).toBe(true);
		const dark = code.modules.flat().filter(Boolean).length;
		const drawn = [...path.matchAll(/h(\d+)v1/g)].reduce((sum, m) => sum + Number(m[1]), 0);
		expect(drawn).toBe(dark);
	});
});
