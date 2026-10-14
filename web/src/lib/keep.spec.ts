import { describe, expect, it } from 'vitest';
import type { SyncRule } from './api/types';
import { SCREENSHOTS, choiceFor, ruleFor, ruleLabel, splitRules } from './keep';

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
