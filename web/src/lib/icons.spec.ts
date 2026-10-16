import { describe, expect, it } from 'vitest';
import { ICONS } from './icons';

describe('icons', () => {
	it('has the icons the shell and the action bars need', () => {
		expect(Object.keys(ICONS).sort()).toEqual([
			'album',
			'alert',
			'back',
			'calendar',
			'camera',
			'check',
			'chevron',
			'close',
			'cloud',
			'collections',
			'crop',
			'date',
			'disk',
			'download',
			'edit',
			'favourite',
			'flip',
			'folder',
			'fullscreen',
			'grid',
			'hidden',
			'home',
			'inbox',
			'info',
			'library',
			'lock',
			'minus',
			'moon',
			'more',
			'pause',
			'person',
			'phone',
			'pin',
			'pinned',
			'play',
			'plus',
			'power',
			'refresh',
			'report',
			'restore',
			'rotate',
			'search',
			'select',
			'share',
			'shield',
			'signout',
			'sliders',
			'sparkle',
			'straighten',
			'sun',
			'text',
			'trash',
			'up',
			'upload',
			'x',
			'zoom'
		]);
	});
	it.each(Object.entries(ICONS))(
		'%s is drawn from absolute paths inside the 24 grid',
		(_, paths) => {
			expect(paths.length).toBeGreaterThan(0);
			for (const d of paths) {
				expect(d).toMatch(/^M/);
				const first = d.match(/^M\s*(-?[\d.]+)[ ,](-?[\d.]+)/);
				expect(first).not.toBeNull();
				for (const n of first!.slice(1).map(Number)) {
					expect(n).toBeGreaterThanOrEqual(0);
					expect(n).toBeLessThanOrEqual(24);
				}
			}
		}
	);
});
