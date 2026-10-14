/**
 * The Who question asks the server's person filter (`person_id`): one person at a time from
 * the chip's sheet, though a link may carry several (FilterChips, WhoQuestion).
 */
import type { AssetFilters, Id } from './api/types';

export const WHO_AVAILABLE = true;

export const chosenPerson = (f: AssetFilters): Id | undefined => f.person_id?.[0];

export function withPerson(f: AssetFilters, id: Id | undefined): AssetFilters {
	const next = { ...f };
	if (id === undefined) delete next.person_id;
	else next.person_id = [id];
	return next;
}
