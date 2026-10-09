/**
 * What a look sets on the page: two attributes and a few CSS variables on the root element,
 * which themes.css and tokens.css read. A null value means "remove it", so going back to the
 * defaults leaves nothing behind. The first-paint script in app.html sets the same from the
 * cached sheet; boot.spec.ts keeps the two equal.
 */
import type { Look } from './sheet';

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

/** Raised surfaces are rounder than controls by this much (12 px → 20 px in Safelight). */
const SURFACE_PER_CONTROL = 5 / 3;

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
