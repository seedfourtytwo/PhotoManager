/**
 * The Who chip asks the server's person filter (`person_id`, spec §10), which another branch is
 * adding to the API. Until `AssetFilters` has it the chip stays away; the chip, its sheet and
 * its answer are built (FilterChips, WhoQuestion), so wiring it is these three lines:
 * `WHO_AVAILABLE = true`, `chosenPerson` reads `f.person_id?.[0]`, `withPerson` sets
 * `person_id: [id]`, and `QUESTION_KEYS.who` (lib/questions.ts) names `person_id`.
 */
import type { AssetFilters, Id } from './api/types';

export const WHO_AVAILABLE = false;

export const chosenPerson = (_f: AssetFilters): Id | undefined => undefined;

export const withPerson = (f: AssetFilters, _id: Id | undefined): AssetFilters => f;
