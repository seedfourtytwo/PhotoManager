/**
 * A QR code for a short piece of text (a link), drawn without a library.
 *
 * Deliberately small: byte mode only, error correction level M only (the usual choice for a
 * code read off a screen), versions 1 to 10 (up to 213 bytes, a link is about 90). The
 * standard is ISO/IEC 18004; the steps below are named as it names them. Checked against an
 * independent encoder and read back by an independent decoder (docs/contracts/qr-cases.json).
 */

/** `modules[y][x]` is true for a dark square. No quiet zone: the drawing adds it. */
export type QrCode = { version: number; size: number; mask: number; modules: boolean[][] };

export const MAX_BYTES = 213;
export const QUIET_ZONE = 4;

// Level M, versions 1 to 10: [all codewords, error-correction codewords per block, blocks]
const VERSIONS: [number, number, number][] = [
	[26, 10, 1],
	[44, 16, 1],
	[70, 26, 1],
	[100, 18, 2],
	[134, 24, 2],
	[172, 16, 4],
	[196, 18, 4],
	[242, 22, 4],
	[292, 22, 5],
	[346, 26, 5]
];
// Centres of the alignment patterns, per version (the same list for rows and columns).
const ALIGNMENT: number[][] = [
	[],
	[6, 18],
	[6, 22],
	[6, 26],
	[6, 30],
	[6, 34],
	[6, 22, 38],
	[6, 24, 42],
	[6, 26, 46],
	[6, 28, 50]
];
const LEVEL_M = 0b00; // the two format bits of level M
const PAD = [0xec, 0x11];

const dataCodewords = (version: number) => {
	const [total, ecc, blocks] = VERSIONS[version - 1];
	return total - ecc * blocks;
};
/** Bits before the bytes: the mode (4) and how many bytes follow (8, from version 10 on 16). */
const headerBits = (version: number) => 4 + (version < 10 ? 8 : 16);

/** How many bytes a code of this version holds. */
export function capacity(version: number): number {
	return Math.floor((dataCodewords(version) * 8 - headerBits(version)) / 8);
}

/** The smallest version that holds this many bytes. */
export function versionFor(bytes: number): number {
	for (let version = 1; version <= VERSIONS.length; version++)
		if (bytes <= capacity(version)) return version;
	throw new RangeError(`too long for a QR code here: ${bytes} bytes, at most ${MAX_BYTES}`);
}

// --- Reed-Solomon over GF(256), the code's error correction -----------------------------------

function multiply(x: number, y: number): number {
	let z = 0;
	for (let i = 7; i >= 0; i--) {
		z = (z << 1) ^ ((z >>> 7) * 0x11d);
		z ^= ((y >>> i) & 1) * x;
	}
	return z;
}

/** The generator polynomial for `degree` check bytes (highest power first, leading 1 left out). */
function generator(degree: number): number[] {
	const result = new Array<number>(degree).fill(0);
	result[degree - 1] = 1;
	let root = 1;
	for (let i = 0; i < degree; i++) {
		for (let j = 0; j < degree; j++) {
			result[j] = multiply(result[j], root);
			if (j + 1 < degree) result[j] ^= result[j + 1];
		}
		root = multiply(root, 2);
	}
	return result;
}

/** The check bytes of one block. */
export function checkBytes(data: number[], degree: number): number[] {
	const divisor = generator(degree);
	const result = new Array<number>(degree).fill(0);
	for (const byte of data) {
		const factor = byte ^ (result.shift() as number);
		result.push(0);
		divisor.forEach((coefficient, i) => (result[i] ^= multiply(coefficient, factor)));
	}
	return result;
}

// --- from text to the final sequence of codewords ---------------------------------------------

function dataBytes(bytes: Uint8Array, version: number): number[] {
	const bits: number[] = [];
	const push = (value: number, length: number) => {
		for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1);
	};
	push(0b0100, 4); // byte mode
	push(bytes.length, headerBits(version) - 4);
	bytes.forEach((byte) => push(byte, 8));
	const room = dataCodewords(version) * 8;
	push(0, Math.min(4, room - bits.length)); // terminator
	push(0, (8 - (bits.length % 8)) % 8);
	const result: number[] = [];
	for (let i = 0; i < bits.length; i += 8)
		result.push(bits.slice(i, i + 8).reduce((byte, bit) => (byte << 1) | bit, 0));
	for (let i = 0; result.length < room / 8; i++) result.push(PAD[i % 2]);
	return result;
}

/** Split into blocks, give each its check bytes, and interleave them as the standard orders. */
function withErrorCorrection(data: number[], version: number): number[] {
	const [, ecc, blocks] = VERSIONS[version - 1];
	const short = Math.floor(data.length / blocks);
	const longBlocks = data.length % blocks; // the last ones, each one byte longer
	const parts: number[][] = [];
	for (let i = 0, at = 0; i < blocks; i++) {
		const length = short + (i >= blocks - longBlocks ? 1 : 0);
		parts.push(data.slice(at, at + length));
		at += length;
	}
	const checks = parts.map((part) => checkBytes(part, ecc));
	const result: number[] = [];
	for (let i = 0; i <= short; i++)
		for (const part of parts) if (i < part.length) result.push(part[i]);
	for (let i = 0; i < ecc; i++) for (const check of checks) result.push(check[i]);
	return result;
}

// --- the grid -----------------------------------------------------------------------------------

class Grid {
	readonly version: number;
	readonly size: number;
	readonly dark: boolean[][];
	/** Squares of the fixed patterns: never data, never masked. */
	readonly fixed: boolean[][];

	constructor(version: number) {
		this.version = version;
		this.size = version * 4 + 17;
		this.dark = Array.from({ length: this.size }, () => new Array<boolean>(this.size).fill(false));
		this.fixed = this.dark.map((row) => [...row]);
		this.drawPatterns();
	}

	private set(x: number, y: number, dark: boolean) {
		this.dark[y][x] = dark;
		this.fixed[y][x] = true;
	}

	private drawPatterns() {
		const last = this.size - 1;
		for (let i = 0; i < this.size; i++) {
			this.set(6, i, i % 2 === 0); // timing
			this.set(i, 6, i % 2 === 0);
		}
		for (const [cx, cy] of [
			[3, 3],
			[last - 3, 3],
			[3, last - 3]
		])
			this.drawFinder(cx, cy);
		const centres = ALIGNMENT[this.version - 1];
		const end = centres.length - 1;
		centres.forEach((cy, i) =>
			centres.forEach((cx, j) => {
				// not where a finder pattern is
				const corner = (i === 0 && j === 0) || (i === 0 && j === end) || (i === end && j === 0);
				if (!corner) this.drawAlignment(cx, cy);
			})
		);
		this.drawFormat(0); // reserves the squares; the real bits come with the mask
		this.drawVersion();
	}

	/** A finder pattern with its light border, wherever it falls inside the grid. */
	private drawFinder(cx: number, cy: number) {
		for (let dy = -4; dy <= 4; dy++)
			for (let dx = -4; dx <= 4; dx++) {
				const distance = Math.max(Math.abs(dx), Math.abs(dy));
				const [x, y] = [cx + dx, cy + dy];
				if (x >= 0 && x < this.size && y >= 0 && y < this.size)
					this.set(x, y, distance !== 2 && distance !== 4);
			}
	}

	private drawAlignment(cx: number, cy: number) {
		for (let dy = -2; dy <= 2; dy++)
			for (let dx = -2; dx <= 2; dx++)
				this.set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
	}

	/** The 15 format bits (level and mask, with their own error correction), written twice. */
	drawFormat(mask: number) {
		const data = (LEVEL_M << 3) | mask;
		let rem = data;
		for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
		const bits = ((data << 10) | rem) ^ 0x5412;
		const bit = (i: number) => ((bits >>> i) & 1) !== 0;
		const last = this.size - 1;
		for (let i = 0; i <= 5; i++) this.set(8, i, bit(i));
		this.set(8, 7, bit(6));
		this.set(8, 8, bit(7));
		this.set(7, 8, bit(8));
		for (let i = 9; i < 15; i++) this.set(14 - i, 8, bit(i));
		for (let i = 0; i < 8; i++) this.set(last - i, 8, bit(i));
		for (let i = 8; i < 15; i++) this.set(8, this.size - 15 + i, bit(i));
		this.set(8, this.size - 8, true); // always dark
	}

	/** From version 7 on: the 18 version bits, written twice. */
	private drawVersion() {
		if (this.version < 7) return;
		let rem = this.version;
		for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
		const bits = (this.version << 12) | rem;
		for (let i = 0; i < 18; i++) {
			const dark = ((bits >>> i) & 1) !== 0;
			const [a, b] = [this.size - 11 + (i % 3), Math.floor(i / 3)];
			this.set(a, b, dark);
			this.set(b, a, dark);
		}
	}

	/** The codewords, in the standard's zigzag: two columns at a time, from the right. */
	drawCodewords(codewords: number[]) {
		let i = 0;
		for (let right = this.size - 1; right >= 1; right -= 2) {
			if (right === 6) right = 5; // the timing column is skipped
			for (let step = 0; step < this.size; step++)
				for (let j = 0; j < 2; j++) {
					const x = right - j;
					const upward = ((right + 1) & 2) === 0;
					const y = upward ? this.size - 1 - step : step;
					if (this.fixed[y][x] || i >= codewords.length * 8) continue;
					this.dark[y][x] = ((codewords[i >>> 3] >>> (7 - (i & 7))) & 1) !== 0;
					i++;
				}
		}
	}

	/** Flip the data squares the mask picks. Applying it twice undoes it. */
	applyMask(mask: number) {
		for (let y = 0; y < this.size; y++)
			for (let x = 0; x < this.size; x++)
				if (!this.fixed[y][x] && MASKS[mask](x, y)) this.dark[y][x] = !this.dark[y][x];
	}
}

const MASKS: ((x: number, y: number) => boolean)[] = [
	(x, y) => (x + y) % 2 === 0,
	(_, y) => y % 2 === 0,
	(x) => x % 3 === 0,
	(x, y) => (x + y) % 3 === 0,
	(x, y) => (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0,
	(x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
	(x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
	(x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0
];

// --- choosing the mask: the standard's four penalties --------------------------------------------

/** Runs of five or more of one colour, and the finder-like 1:1:3:1:1 with four light beside it. */
function linePenalty(line: boolean[]): number {
	let penalty = 0;
	for (let i = 0; i < line.length;) {
		let j = i;
		while (j < line.length && line[j] === line[i]) j++;
		if (j - i >= 5) penalty += 3 + (j - i - 5);
		i = j;
	}
	const at = (i: number) => i >= 0 && i < line.length && line[i];
	const FINDER = [true, false, true, true, true, false, true];
	for (let i = 0; i + 7 <= line.length; i++) {
		if (!FINDER.every((dark, k) => line[i + k] === dark)) continue;
		const lightBefore = [1, 2, 3, 4].every((k) => !at(i - k));
		const lightAfter = [7, 8, 9, 10].every((k) => !at(i + k));
		if (lightBefore || lightAfter) penalty += 40;
	}
	return penalty;
}

export function penalty(modules: boolean[][]): number {
	const size = modules.length;
	let result = 0;
	let dark = 0;
	for (let y = 0; y < size; y++) {
		result += linePenalty(modules[y]);
		result += linePenalty(modules.map((row) => row[y]));
		for (let x = 0; x < size; x++) {
			if (modules[y][x]) dark++;
			if (x + 1 < size && y + 1 < size) {
				const colour = modules[y][x];
				if (
					modules[y][x + 1] === colour &&
					modules[y + 1][x] === colour &&
					modules[y + 1][x + 1] === colour
				)
					result += 3;
			}
		}
	}
	const percent = (dark * 100) / (size * size);
	result += Math.floor(Math.abs(percent - 50) / 5) * 10;
	return result;
}

// --- the whole thing ---------------------------------------------------------------------------

/**
 * The QR code of `text` (UTF-8). `mask` forces one of the eight masks (tests compare with
 * another encoder's choice); left out, the one with the lowest penalty is used.
 */
export function encode(text: string, options: { mask?: number } = {}): QrCode {
	const bytes = new TextEncoder().encode(text);
	const version = versionFor(bytes.length);
	const grid = new Grid(version);
	grid.drawCodewords(withErrorCorrection(dataBytes(bytes, version), version));
	let mask = options.mask ?? -1;
	if (mask < 0) {
		let best = Infinity;
		for (let candidate = 0; candidate < MASKS.length; candidate++) {
			grid.applyMask(candidate);
			grid.drawFormat(candidate);
			const score = penalty(grid.dark);
			if (score < best) [best, mask] = [score, candidate];
			grid.applyMask(candidate); // undo
		}
	}
	grid.applyMask(mask);
	grid.drawFormat(mask);
	return { version, size: grid.size, mask, modules: grid.dark };
}

/** One SVG path for the dark squares, inside a quiet zone of four light squares all round. */
export function svgPath(code: QrCode): { path: string; viewBox: string } {
	const parts: string[] = [];
	code.modules.forEach((row, y) => {
		for (let x = 0; x < row.length; x++) {
			if (!row[x]) continue;
			let run = 1;
			while (x + run < row.length && row[x + run]) run++;
			parts.push(`M${x + QUIET_ZONE} ${y + QUIET_ZONE}h${run}v1h-${run}z`);
			x += run;
		}
	});
	const side = code.size + 2 * QUIET_ZONE;
	return { path: parts.join(''), viewBox: `0 0 ${side} ${side}` };
}
