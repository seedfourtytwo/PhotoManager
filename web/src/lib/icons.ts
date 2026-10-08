/** Icons drawn for this app on a 24 × 24 grid: stroked paths, no fills (DESIGN_PRINCIPLES §2). */
export const ICONS = {
	library: ['M4 4h7v7H4z', 'M13 4h7v7h-7z', 'M4 13h7v7H4z', 'M13 13h7v7h-7z'],
	collections: ['M4 9h16v11H4z', 'M6.5 6h11', 'M8.5 3.2h7'],
	search: ['M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0z', 'M20 20l-4.6-4.6']
} as const satisfies Record<string, readonly string[]>;

export type IconName = keyof typeof ICONS;
