/**
 * Keep on my phone (FEATURES 10.6): which rule of a device names a thing, and rules in words.
 * The server merges the rules into the device's list; the app only shows and edits them.
 */
import type { AssetFilters, SyncMode, SyncRule, SyncTarget } from './api/types';
import { describeFilters, filtersToQuery } from './filters';
import { plural } from './format';

/** "Leave out screenshots": the search facet the auto-tagger answers (needs its models). */
const SCREENSHOT_FILTERS: AssetFilters = { q: 'tag:screenshot' };
export const SCREENSHOTS: SyncTarget = { kind: 'filter', filters: SCREENSHOT_FILTERS };
const sameFilters = (a: AssetFilters | null, b: AssetFilters) =>
	filtersToQuery(a ?? {}) === filtersToQuery(b);

export type Choice = SyncMode | 'none';

/** The device's rule naming this album, person or these filters (written in any order). */
export function ruleFor(rules: readonly SyncRule[], target: SyncTarget): SyncRule | undefined {
	return rules.find((rule) => {
		if (rule.kind !== target.kind) return false;
		if (target.kind === 'album') return rule.album_id === target.album_id;
		if (target.kind === 'person') return rule.person_id === target.person_id;
		return sameFilters(rule.filters, target.filters);
	});
}

export function choiceFor(rules: readonly SyncRule[], target: SyncTarget): Choice {
	return ruleFor(rules, target)?.mode ?? 'none';
}

const GONE = { album: 'An album', person: 'Someone', filter: 'Filters' } as const;

export function ruleLabel(rule: SyncRule): string {
	if (rule.gone) return `${GONE[rule.kind]} no longer there`;
	if (rule.kind === 'album') return rule.label ?? 'An album';
	if (rule.kind === 'person') return rule.label ?? 'Someone without a name';
	if (sameFilters(rule.filters, SCREENSHOT_FILTERS)) return 'Screenshots';
	return describeFilters(rule.filters ?? {}) || 'All photos';
}

export function splitRules(rules: readonly SyncRule[]) {
	return {
		keeps: rules.filter((r) => r.mode === 'include'),
		leavesOff: rules.filter((r) => r.mode === 'exclude')
	};
}

const WHERE = {
	album: (photos: string) => `${photos} in this album`,
	person: (photos: string) => `${photos} of this person`,
	filter: (photos: string) => `${photos.split(' ')[0]} of these photos`
} as const;

/**
 * Why a kept album (or person, or search) holds photos that never reach the phone: the user
 * may only view them (an album grants view, not download). Null when there are none.
 */
export function viewOnlyNote(rule: SyncRule): string | null {
	const n = rule.mode === 'include' ? rule.view_only : 0;
	if (!n) return null;
	const them = n === 1 ? 'it' : 'them';
	return `${WHERE[rule.kind](plural(n, 'photo'))} can’t go to your phone: you can only view ${them}.`;
}
