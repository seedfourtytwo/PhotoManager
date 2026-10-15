/**
 * What a look sets on the page: two attributes and a few CSS variables on the root element,
 * which themes.css and tokens.css read. A null value means "remove it", so going back to the
 * defaults leaves nothing behind. The first-paint script in app.html sets the same from the
 * cached sheet; boot.spec.ts keeps the two equal.
 */
import type { Look, Mode, Theme } from './sheet';

/** The three dials a look may leave to its theme, as numbers. */
export type ThemeDials = { accentHue: number; corners: number; photoGap: number };

/** The accent hue (per mode), the corners and the gap between photos (px) each theme has in
 *  themes.css and tokens.css. */
const THEMES_OWN: Record<
	Theme,
	{ accentHue: { dark: number; light: number }; corners: number; photoGap: number }
> = {
	safelight: { accentHue: { dark: 72, light: 72 }, corners: 14, photoGap: 2 },
	album: { accentHue: { dark: 281, light: 275 }, corners: 3, photoGap: 3 }
};

/**
 * What a theme itself gives the dials a look can leave to it: the one place that says so
 * outside the stylesheets (apply.spec.ts keeps them equal). The look form starts a dial
 * there, and the grid takes its gap from it. Following the device counts as dark.
 */
export function themeDials(theme: Theme, mode: Mode): ThemeDials {
	const { accentHue, corners, photoGap } = THEMES_OWN[theme];
	return { accentHue: accentHue[mode === 'light' ? 'light' : 'dark'], corners, photoGap };
}

export type RootLook = {
	attributes: Record<'data-look' | 'data-theme', string | null>;
	variables: Record<'--acc-h' | '--r-1' | '--r-2' | '--gutter' | '--text-scale', string | null>;
};

/** The part of an element a look touches (the root element; a stand-in under test). */
export type LookRoot = {
	setAttribute(name: string, value: string): void;
	removeAttribute(name: string): void;
	style: { setProperty(name: string, value: string): void; removeProperty(name: string): string };
};

/** Raised surfaces are rounder than controls by this much (14 px → 28 px in Safelight). */
const SURFACE_PER_CONTROL = 2;

const px = (value: number | null) => (value === null ? null : `${value}px`);

export function rootLook(look: Look): RootLook {
	return {
		attributes: {
			// absent = Safelight, and absent = follow the device (themes.css)
			'data-look': look.theme === 'safelight' ? null : look.theme,
			'data-theme': look.mode === 'system' ? null : look.mode
		},
		variables: {
			'--acc-h': look.accentHue === null ? null : String(look.accentHue),
			'--r-1': px(look.corners),
			'--r-2': px(look.corners === null ? null : Math.round(look.corners * SURFACE_PER_CONTROL)),
			'--gutter': px(look.photoGap),
			'--text-scale': look.textScale === 1 ? null : String(look.textScale)
		}
	};
}

export function applyLook(look: Look, root: LookRoot = document.documentElement) {
	const { attributes, variables } = rootLook(look);
	for (const [name, value] of Object.entries(attributes))
		if (value === null) root.removeAttribute(name);
		else root.setAttribute(name, value);
	for (const [name, value] of Object.entries(variables))
		if (value === null) root.style.removeProperty(name);
		else root.style.setProperty(name, value);
}
