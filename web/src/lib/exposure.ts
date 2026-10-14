/**
 * How a photo was exposed, as the photo view writes it ("f/2.8 · 1/250 s · ISO 400 · 35 mm")
 * and as a screen reader says it. Each value stands on its own: what the photo does not
 * carry is left out.
 */
import type { AssetDetail } from './api/types';

export type Exposure = Pick<AssetDetail, 'f_number' | 'exposure_time' | 'iso' | 'focal_length'>;

/** Below this a shutter time is written as a fraction, as cameras and ExifTool do: 1/4 s, then 0.3 s. */
const FRACTION_BELOW_SECONDS = 0.25001;

/** A value the server sends is clean; one that is not (0, negative, not a number) is unknown. */
const known = (value: number | null): value is number =>
	value !== null && Number.isFinite(value) && value > 0;

/** At most `places` decimals, none for a whole number: 2.8, 11, 4.3. */
const short = (value: number, places = 1) => String(Number(value.toFixed(places)));

/** "1/250" or "2.5": the number alone, for both the written and the spoken form. */
function shutterNumber(seconds: number): string {
	return seconds < FRACTION_BELOW_SECONDS ? `1/${Math.round(1 / seconds)}` : short(seconds);
}

export function shutterText(seconds: number): string {
	return `${shutterNumber(seconds)} s`;
}

/** A lens faster than f/1 needs its second decimal: f/0.95. */
const aperture = (f: number) => short(f, f < 1 ? 2 : 1);

/** The known values in the order a camera shows them: aperture, shutter, ISO, focal length. */
export function exposureParts(exposure: Exposure | null): string[] {
	if (!exposure) return [];
	const { f_number, exposure_time, iso, focal_length } = exposure;
	return [
		known(f_number) ? `f/${aperture(f_number)}` : null,
		known(exposure_time) ? shutterText(exposure_time) : null,
		known(iso) ? `ISO ${iso}` : null,
		known(focal_length) ? `${short(focal_length)} mm` : null
	].filter((part) => part !== null);
}

const counted = (number: string, unit: string) => `${number} ${unit}${number === '1' ? '' : 's'}`;

/** The same values in words: "f 2.8", "1/250 second", "ISO 400", "35 millimetres". */
export function exposureSpoken(exposure: Exposure | null): string[] {
	if (!exposure) return [];
	const { f_number, exposure_time, iso, focal_length } = exposure;
	const shutter = known(exposure_time) ? shutterNumber(exposure_time) : null;
	return [
		known(f_number) ? `f ${aperture(f_number)}` : null,
		// A fraction of a second is one "second" ("one two-hundred-and-fiftieth second").
		shutter && (shutter.includes('/') ? `${shutter} second` : counted(shutter, 'second')),
		known(iso) ? `ISO ${iso}` : null,
		known(focal_length) ? counted(short(focal_length), 'millimetre') : null
	].filter((part) => part !== null);
}
