import { describe, expect, it } from 'vitest';
import themes from '../themes.css?raw';
import tokens from '../tokens.css?raw';
import { readBlocks } from '../testing/css-blocks';
import { applyLook, rootLook, themeDials, type LookRoot } from './apply';
import { parseLook, type Mode, type Theme } from './sheet';

const styles = Object.values(
	import.meta.glob(['/src/**/*.svelte', '/src/**/*.css'], {
		query: '?raw',
		import: 'default',
		eager: true
	}) as Record<string, string>
).join('\n');

const NOTHING = {
	'--acc-h': null,
	'--r-1': null,
	'--r-2': null,
	'--gutter': null,
	'--text-scale': null
};

/** Stands in for the root element: what was set, and nothing that was removed. */
function fakeRoot(attributes: Record<string, string> = {}, variables: Record<string, string> = {}) {
	const root: LookRoot = {
		setAttribute: (name, value) => void (attributes[name] = value),
		removeAttribute: (name) => void delete attributes[name],
		style: {
			setProperty: (name, value) => void (variables[name] = value),
			removeProperty: (name) => (delete variables[name], '')
		}
	};
	return { root, attributes, variables };
}

describe('rootLook', () => {
	it('the default look sets the dark mode and no variable', () => {
		expect(rootLook(parseLook({}))).toEqual({
			attributes: { 'data-look': null, 'data-theme': 'dark' },
			variables: NOTHING
		});
	});

	it('the Album theme is an attribute, Safelight is its absence', () => {
		expect(rootLook(parseLook({ theme: 'album' })).attributes['data-look']).toBe('album');
		expect(rootLook(parseLook({ theme: 'safelight' })).attributes['data-look']).toBeNull();
	});

	it('following the device removes the mode attribute', () => {
		expect(rootLook(parseLook({ mode: 'system' })).attributes['data-theme']).toBeNull();
		expect(rootLook(parseLook({ mode: 'light' })).attributes['data-theme']).toBe('light');
	});

	it('each dial becomes its variable', () => {
		const look = parseLook({ accentHue: 200, corners: 6, photoGap: 4, textScale: 1.15 });
		expect(rootLook(look).variables).toEqual({
			'--acc-h': '200',
			'--r-1': '6px',
			'--r-2': '10px',
			'--gutter': '4px',
			'--text-scale': '1.15'
		});
	});

	it('corners move both radii, 12 gives the Safelight pair and zero is square', () => {
		expect(rootLook(parseLook({ corners: 12 })).variables).toMatchObject({
			'--r-1': '12px',
			'--r-2': '20px'
		});
		expect(rootLook(parseLook({ corners: 0 })).variables).toMatchObject({
			'--r-1': '0px',
			'--r-2': '0px'
		});
	});

	it('a hue of zero is a hue, not "the theme\'s own"', () => {
		expect(rootLook(parseLook({ accentHue: 0, photoGap: 0 })).variables).toMatchObject({
			'--acc-h': '0',
			'--gutter': '0px'
		});
	});
});

describe('the stylesheets', () => {
	it.each(Object.keys(NOTHING))('read %s, so the dial does something', (name) => {
		expect(styles).toContain(`var(${name}`);
	});
});

describe('themeDials (where a dial stands while it is left to the theme)', () => {
	const colours = readBlocks(themes);
	const shapes = readBlocks(tokens);

	it.each<[Theme, Mode, string, string]>([
		['safelight', 'dark', ':root', ':root'],
		['safelight', 'light', ":root[data-theme='light']", ':root'],
		['album', 'dark', ":root[data-look='album']", ":root[data-look='album']"],
		['album', 'light', ":root[data-look='album'][data-theme='light']", ":root[data-look='album']"]
	])('%s %s has the accent and corners of the stylesheets', (theme, mode, colour, shape) => {
		expect(themeDials(theme, mode)).toMatchObject({
			accentHue: Number(colours.get(colour)?.['--acc-h']),
			corners: parseInt(shapes.get(shape)?.['--r-1'] ?? '')
		});
	});

	it('differs between the themes, so one theme’s values cannot stand in for the other’s', () => {
		expect(themeDials('safelight', 'dark')).toEqual({ accentHue: 72, corners: 12, photoGap: 3 });
		expect(themeDials('album', 'dark')).toEqual({ accentHue: 281, corners: 3, photoGap: 3 });
		expect(themeDials('album', 'light').accentHue).toBe(275);
	});

	it('following the device counts as dark, the mode a look starts in', () => {
		expect(themeDials('album', 'system')).toEqual(themeDials('album', 'dark'));
	});
});

describe('applyLook', () => {
	it('sets the attributes and variables on the root', () => {
		const { root, attributes, variables } = fakeRoot();
		applyLook(parseLook({ theme: 'album', mode: 'light', accentHue: 30 }), root);
		expect(attributes).toEqual({ 'data-look': 'album', 'data-theme': 'light' });
		expect(variables).toEqual({ '--acc-h': '30' });
	});

	it('going back to the defaults removes everything an earlier look set', () => {
		const { root, attributes, variables } = fakeRoot();
		applyLook(
			parseLook({
				theme: 'album',
				mode: 'system',
				accentHue: 30,
				corners: 2,
				photoGap: 1,
				textScale: 1.2
			}),
			root
		);
		applyLook(parseLook({}), root);
		expect(attributes).toEqual({ 'data-theme': 'dark' });
		expect(variables).toEqual({});
	});

	it('leaves alone what is not the look’s', () => {
		const { root, attributes, variables } = fakeRoot({ lang: 'en' }, { '--other': '1' });
		applyLook(parseLook({}), root);
		expect(attributes).toEqual({ lang: 'en', 'data-theme': 'dark' });
		expect(variables).toEqual({ '--other': '1' });
	});
});
