import { describe, expect, it } from 'vitest';
import type { SyncRule } from './api/types';
import { SCREENSHOTS, choiceFor, ruleFor, ruleLabel, splitRules, viewOnlyNote } from './keep';

function rule(over: Partial<SyncRule>): SyncRule {
	return {
		id: 1,
		kind: 'album',
		mode: 'include',
		album_id: null,
		person_id: null,
		filters: null,
		label: null,
		count: 0,
		gone: false,
		view_only: 0,
		...over
	};
}

const summer = rule({ id: 1, album_id: 7, label: 'Summer', count: 40 });
const lea = rule({ id: 2, kind: 'person', person_id: 3, label: 'Léa', mode: 'exclude' });
const shots = rule({ id: 3, kind: 'filter', filters: { q: 'tag:screenshot' }, mode: 'exclude' });
const year = rule({ id: 4, kind: 'filter', filters: { year: 2019, place: 'Paris' } });

describe('which rule names a thing', () => {
	it('finds an album or a person by its id', () => {
		expect(ruleFor([summer, lea], { kind: 'album', album_id: 7 })).toBe(summer);
		expect(ruleFor([summer, lea], { kind: 'person', person_id: 3 })).toBe(lea);
		expect(ruleFor([summer, lea], { kind: 'album', album_id: 3 })).toBeUndefined();
		expect(ruleFor([summer, lea], { kind: 'person', person_id: 7 })).toBeUndefined();
	});

	it('finds filters by what they mean, not by the order they were written in', () => {
		const same = { kind: 'filter', filters: { place: 'Paris', year: 2019 } } as const;
		expect(ruleFor([summer, year], same)).toBe(year);
		const other = { kind: 'filter', filters: { year: 2019 } } as const;
		expect(ruleFor([summer, year], other)).toBeUndefined();
	});

	it('says what a device does with it: keep, leave off, or nothing chosen', () => {
		expect(choiceFor([summer, lea], { kind: 'album', album_id: 7 })).toBe('include');
		expect(choiceFor([summer, lea], { kind: 'person', person_id: 3 })).toBe('exclude');
		expect(choiceFor([summer, lea], SCREENSHOTS)).toBe('none');
		expect(choiceFor([shots], SCREENSHOTS)).toBe('exclude');
	});
});

describe('rules in words', () => {
	it('names albums and people, describes filters', () => {
		expect(ruleLabel(summer)).toBe('Summer');
		expect(ruleLabel(lea)).toBe('Léa');
		expect(ruleLabel(year)).toBe('2019 · Paris');
		expect(ruleLabel(shots)).toBe('Screenshots');
		expect(ruleLabel(rule({ kind: 'filter', filters: {} }))).toBe('All photos');
	});

	it('says when what a rule named is no longer there', () => {
		expect(ruleLabel(rule({ gone: true }))).toBe('An album no longer there');
		expect(ruleLabel(rule({ kind: 'person', gone: true }))).toBe('Someone no longer there');
		expect(ruleLabel(rule({ kind: 'person', label: null }))).toBe('Someone without a name');
	});

	it('splits a device’s rules into what it keeps and what it leaves off', () => {
		expect(splitRules([summer, lea, shots, year])).toEqual({
			keeps: [summer, year],
			leavesOff: [lea, shots]
		});
	});
});

describe('photos that cannot go', () => {
	it('says plainly how many of a kept album’s photos she may only view', () => {
		expect(viewOnlyNote({ ...summer, view_only: 12 })).toBe(
			'12 photos in this album can’t go to your phone: you can only view them.'
		);
		expect(viewOnlyNote({ ...summer, view_only: 1 })).toBe(
			'1 photo in this album can’t go to your phone: you can only view it.'
		);
		expect(viewOnlyNote({ ...lea, mode: 'include', view_only: 3 })).toBe(
			'3 photos of this person can’t go to your phone: you can only view them.'
		);
		expect(viewOnlyNote({ ...year, view_only: 2 })).toBe(
			'2 of these photos can’t go to your phone: you can only view them.'
		);
	});

	it('says nothing when every photo can go, or for what is left off', () => {
		expect(viewOnlyNote(summer)).toBeNull();
		expect(viewOnlyNote({ ...lea, view_only: 4 })).toBeNull();
	});
});
