import { describe, expect, it } from 'vitest';
import { applyLook, rootLook, type LookRoot } from './apply';
import { parseLook } from './sheet';

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
