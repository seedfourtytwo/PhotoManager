/** Icons drawn for this app on a 24 × 24 grid: stroked paths, no fills (DESIGN_PRINCIPLES §2). */
export const ICONS = {
	library: ['M4 4h7v7H4z', 'M13 4h7v7h-7z', 'M4 13h7v7H4z', 'M13 13h7v7h-7z'],
	collections: ['M4 9h16v11H4z', 'M6.5 6h11', 'M8.5 3.2h7'],
	search: ['M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0z', 'M20 20l-4.6-4.6'],
	favourite: ['M12 20s-7-4.4-7-9.6A3.9 3.9 0 0 1 12 8a3.9 3.9 0 0 1 7 2.4C19 15.6 12 20 12 20z'],
	album: [
		'M6 6h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z',
		'M10.5 10v5',
		'M8 12.5h5',
		'M8 3.5h10a2.5 2.5 0 0 1 2.5 2.5v10'
	],
	download: ['M12 4v11', 'M8 11.5l4 4 4-4', 'M5 20h14'],
	share: ['M12 15V4', 'M8 8l4-4 4 4', 'M8.5 11H6v9h12v-9h-2.5'],
	edit: [
		'M4 7h9',
		'M17 7h3',
		'M4 17h3',
		'M11 17h9',
		'M17 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0z',
		'M11 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0z'
	],
	more: [
		'M7 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0z',
		'M13 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0z',
		'M19 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0z'
	],
	date: ['M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0z', 'M12 7.5V12l3 2'],
	trash: ['M5 7h14', 'M10 7V4.5h4V7', 'M7 7l1 12.5h8L17 7'],
	restore: ['M8 5L4 9l4 4', 'M4 9h10a5 5 0 0 1 0 10h-3'],
	close: ['M6 9l6 6 6-6'],
	info: ['M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0z', 'M12 11v5', 'M12 7.8v.4']
} as const satisfies Record<string, readonly string[]>;

export type IconName = keyof typeof ICONS;
