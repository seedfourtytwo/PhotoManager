/** Colour maths for the theme tests: WCAG relative luminance and contrast ratio. */

const linear = (channel: number) =>
	channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;

const clip = (value: number) => Math.min(1, Math.max(0, value));

const luminance = (r: number, g: number, b: number) => 0.2126 * r + 0.7152 * g + 0.0722 * b;

/** Relative luminance of `#rgb` or `#rrggbb`. */
export function hexLuminance(hex: string): number {
	const digits = hex.replace('#', '');
	const full = digits.length === 3 ? [...digits].map((d) => d + d).join('') : digits;
	const [r, g, b] = [0, 2, 4].map((i) => linear(parseInt(full.slice(i, i + 2), 16) / 255));
	return luminance(r, g, b);
}

/** Relative luminance of `oklch(l c h)`, clipped to sRGB the simple way (per channel). */
export function oklchLuminance(l: number, c: number, hDeg: number): number {
	const h = (hDeg * Math.PI) / 180;
	const a = c * Math.cos(h);
	const b = c * Math.sin(h);
	const lp = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
	const mp = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
	const sp = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
	return luminance(
		clip(4.0767416621 * lp - 3.3077115913 * mp + 0.2309699292 * sp),
		clip(-1.2684380046 * lp + 2.6097574011 * mp - 0.3413193965 * sp),
		clip(-0.0041960863 * lp - 0.7034186147 * mp + 1.707614701 * sp)
	);
}

/** WCAG contrast ratio of two relative luminances, in either order. */
export function contrast(a: number, b: number): number {
	const [hi, lo] = a > b ? [a, b] : [b, a];
	return (hi + 0.05) / (lo + 0.05);
}
