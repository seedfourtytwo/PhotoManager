/**
 * The look of one account: a sheet of named values, never CSS (docs/adr/0001).
 *
 * A hand-kept mirror of backend/src/photo_assistant/domain/look.py, which decides; the same
 * sheets are tested on both sides. Nothing here imports the rest of the app.
 *
 * `parseLook` is strict (a sheet someone sends): an unknown field, a wrong kind or an unknown
 * choice throws, a number outside its range is clamped. `readLook` is forgiving (a sheet that
 * was stored or received): a field that does not pass reads as its default, a field this
 * build does not know is left out, and the rest of the sheet stays. So a newer backend never
 * sends an open tab back to the defaults, and no sheet can make the app unusable.
 *
 * Numbers follow the backend's rule (docs/contracts/look-cases.json is the table both test
 * suites run): clamp first, however far outside the number is, then round a half up.
 */

export const THEMES = ['safelight', 'album'] as const;
export const MODES = ['system', 'dark', 'light'] as const;
/** The typeface of the whole app: Inter, or Atkinson Hyperlegible as "Larger text". */
export const FACES = ['inter', 'atkinson'] as const;
export const THUMB_SIZES = ['small', 'medium', 'large'] as const;
export const START_PAGES = ['today', 'library'] as const;
export const COLLECTIONS_ROWS = ['people', 'places', 'albums'] as const;
/** The blocks of Home, in the order a new account sees them. */
export const HOME_SECTIONS = [
	'on_this_day',
	'rediscover',
	'memories',
	'suggested',
	'years',
	'pinned',
	'people',
	'new'
] as const;
/** What an account sets for itself (`PUT /api/me/look`); an admin sets the rest. */
export const OWN_FIELDS = ['mode', 'homeSections'] as const;

export type Theme = (typeof THEMES)[number];
/** `system` follows the device. */
export type Mode = (typeof MODES)[number];
export type Face = (typeof FACES)[number];
export type ThumbSize = (typeof THUMB_SIZES)[number];
export type StartPage = (typeof START_PAGES)[number];
export type CollectionsRow = (typeof COLLECTIONS_ROWS)[number];
export type HomeSection = (typeof HOME_SECTIONS)[number];
export type OwnChoice = Partial<Pick<Look, (typeof OWN_FIELDS)[number]>>;

export type Look = {
	theme: Theme;
	mode: Mode;
	/** Degrees; null on these three dials means "whatever the theme says". */
	accentHue: number | null;
	/** px */
	corners: number | null;
	/** px */
	photoGap: number | null;
	textScale: number;
	face: Face;
	thumbSize: ThumbSize;
	showToday: boolean;
	startPage: StartPage;
	collectionsRows: CollectionsRow[];
	dockLabels: boolean;
	/** The blocks Home shows, in their order. */
	homeSections: HomeSection[];
};

/** Dials: the lowest and highest value each may take. */
export const LOOK_RANGES = {
	accentHue: [0, 360],
	corners: [0, 22],
	photoGap: [0, 8],
	textScale: [0.9, 1.25]
} as const;

const defaults = (): Look => ({
	theme: 'safelight',
	mode: 'dark',
	accentHue: null,
	corners: null,
	photoGap: null,
	textScale: 1,
	face: 'inter',
	thumbSize: 'medium',
	showToday: true,
	startPage: 'today',
	collectionsRows: [...COLLECTIONS_ROWS],
	dockLabels: true,
	homeSections: [...HOME_SECTIONS]
});

export const DEFAULT_LOOK: Readonly<Look> = Object.freeze({
	...defaults(),
	collectionsRows: Object.freeze([...COLLECTIONS_ROWS]) as unknown as CollectionsRow[],
	homeSections: Object.freeze([...HOME_SECTIONS]) as unknown as HomeSection[]
});

/** A sheet that cannot be a look; the message names the field and what it may hold. */
export class LookError extends Error {}

function number(field: keyof typeof LOOK_RANGES, value: unknown): number {
	const [low, high] = LOOK_RANGES[field];
	// Infinity is what JSON makes of a number too large to hold: far outside, so clamped
	if (typeof value !== 'number' || Number.isNaN(value))
		throw new LookError(`'${field}' must be a number from ${low} to ${high}`);
	return Math.min(Math.max(value, low), high);
}

/** The nearest whole number, a half going up: the same sum as the backend's. */
const halfUp = (value: number) => Math.floor(value + 0.5);

const dial = (field: 'accentHue' | 'corners' | 'photoGap') => (value: unknown) =>
	value === null ? null : halfUp(number(field, value));

const choice =
	<T extends string>(field: string, allowed: readonly T[]) =>
	(value: unknown): T => {
		if (allowed.includes(value as T)) return value as T;
		throw new LookError(`'${field}' must be one of: ${allowed.join(', ')}`);
	};

const toggle = (field: string) => (value: unknown) => {
	if (typeof value === 'boolean') return value;
	throw new LookError(`'${field}' must be true or false`);
};

/** Some of `allowed`, each once, in the order to show them: the ones shown. */
const ordered =
	<T extends string>(field: string, allowed: readonly T[]) =>
	(value: unknown): T[] => {
		const names: unknown[] = Array.isArray(value) ? value : [];
		const chosen = names.filter((name): name is T => allowed.includes(name as T));
		if (
			chosen.length === 0 ||
			chosen.length !== names.length ||
			new Set(chosen).size !== chosen.length
		)
			throw new LookError(
				`'${field}' must list at least one of ${allowed.join(', ')}, ` +
					'each once, in the order to show them'
			);
		return chosen;
	};

/** Every field of the sheet and how its value is read. */
const FIELDS: { [K in keyof Look]: (value: unknown) => Look[K] } = {
	theme: choice('theme', THEMES),
	mode: choice('mode', MODES),
	accentHue: dial('accentHue'),
	corners: dial('corners'),
	photoGap: dial('photoGap'),
	textScale: (value) => halfUp(number('textScale', value) * 100) / 100,
	face: choice('face', FACES),
	thumbSize: choice('thumbSize', THUMB_SIZES),
	showToday: toggle('showToday'),
	startPage: choice('startPage', START_PAGES),
	collectionsRows: ordered('collectionsRows', COLLECTIONS_ROWS),
	dockLabels: toggle('dockLabels'),
	homeSections: ordered('homeSections', HOME_SECTIONS)
};

const isField = (name: string): name is keyof Look => Object.hasOwn(FIELDS, name);

const isSheet = (raw: unknown): raw is object =>
	typeof raw === 'object' && raw !== null && !Array.isArray(raw);

/** The sheet's own fields of `raw`, read; `strict` throws for one that does not pass. */
function fill(raw: object, strict: boolean): Look {
	const look = defaults();
	const assign = <K extends keyof Look>(name: K, value: unknown) => {
		look[name] = FIELDS[name](value);
	};
	for (const [name, value] of Object.entries(raw)) {
		if (!isField(name)) continue;
		try {
			assign(name, value);
		} catch (error) {
			if (strict || !(error instanceof LookError)) throw error;
		}
	}
	if (!look.showToday) look.startPage = 'library'; // no Today tab to start on
	return look;
}

/** The look a sent sheet describes; fields it leaves out take their default. Throws LookError. */
export function parseLook(raw: unknown): Look {
	if (!isSheet(raw)) throw new LookError('a look is an object of named values');
	const unknown = Object.keys(raw)
		.filter((name) => !isField(name))
		.sort();
	if (unknown.length > 0)
		throw new LookError(
			`unknown look field ${unknown.map((name) => `'${name}'`).join(', ')}; ` +
				`a look has only: ${Object.keys(FIELDS).join(', ')}`
		);
	return fill(raw, true);
}

/**
 * The look a stored or received sheet describes: each field that passes, the default for
 * each that does not, and the defaults for something that is not a sheet at all.
 */
export function readLook(raw: unknown): Look {
	return isSheet(raw) ? fill(raw, false) : defaults();
}

/** Whether two looks hold the same values. */
export function sameLook(a: Look, b: Look): boolean {
	return Object.keys(FIELDS).every(
		(name) => isField(name) && JSON.stringify(a[name]) === JSON.stringify(b[name])
	);
}
