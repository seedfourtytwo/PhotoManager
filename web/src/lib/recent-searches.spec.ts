import { describe, expect, it } from 'vitest';
import { RECENT_MAX, forgetRecent, loadRecent, remember, saveRecent } from './recent-searches';

/** A Storage that keeps what it is given, or one that refuses (a private window, a full disk). */
function storage(refuse = false): Storage {
	const kept = new Map<string, string>();
	return {
		get length() {
			return kept.size;
		},
		clear: () => kept.clear(),
		key: (i) => [...kept.keys()][i] ?? null,
		getItem: (k) => {
			if (refuse) throw new Error('denied');
			return kept.get(k) ?? null;
		},
		setItem: (k, v) => {
			if (refuse) throw new Error('denied');
			kept.set(k, v);
		},
		removeItem: (k) => {
			if (refuse) throw new Error('denied');
			kept.delete(k);
		}
	};
}

describe('remembering a search', () => {
	it('puts the newest first', () => {
		expect(remember(['beach'], 'snow')).toEqual(['snow', 'beach']);
	});
	it('a search made again moves to the front, once, whatever its case or spaces', () => {
		expect(remember(['snow', 'Beach', 'dog'], '  beach ')).toEqual(['beach', 'snow', 'dog']);
	});
	it('nothing typed is not a search', () => {
		expect(remember(['snow'], '   ')).toEqual(['snow']);
	});
	it('keeps the latest few only', () => {
		const many = Array.from({ length: RECENT_MAX }, (_, i) => `q${i}`);
		const next = remember(many, 'new');
		expect(next).toHaveLength(RECENT_MAX);
		expect(next[0]).toBe('new');
		expect(next).not.toContain(`q${RECENT_MAX - 1}`);
	});
});

describe('recent searches on this device', () => {
	it('come back as they were saved', () => {
		const store = storage();
		saveRecent(['snow', 'beach'], store);
		expect(loadRecent(store)).toEqual(['snow', 'beach']);
	});
	it('none saved yet: none', () => {
		expect(loadRecent(storage())).toEqual([]);
	});
	it('something unreadable or of another shape is taken as none', () => {
		const store = storage();
		store.setItem('pa.recent-searches', '{not json');
		expect(loadRecent(store)).toEqual([]);
		store.setItem('pa.recent-searches', JSON.stringify([1, 'snow', null]));
		expect(loadRecent(store)).toEqual(['snow']);
		store.setItem('pa.recent-searches', JSON.stringify({ q: 'snow' }));
		expect(loadRecent(store)).toEqual([]);
	});
	it('a device that refuses storage still searches: nothing is kept, nothing breaks', () => {
		const store = storage(true);
		expect(() => saveRecent(['snow'], store)).not.toThrow();
		expect(loadRecent(store)).toEqual([]);
		expect(() => forgetRecent(store)).not.toThrow();
	});
	it('Clear forgets them all', () => {
		const store = storage();
		saveRecent(['snow'], store);
		forgetRecent(store);
		expect(loadRecent(store)).toEqual([]);
	});
});
