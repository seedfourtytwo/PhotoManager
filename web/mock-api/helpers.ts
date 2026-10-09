/** What every route table is handed: the mock's world and the helpers built on it. */
import { accessHelpers } from './access.ts';
import { accountHelpers } from './accounts.ts';
import { filterHelpers } from './filters.ts';
import { jobHelpers } from './jobs.ts';
import { shapeHelpers } from './shapes.ts';
import type { World } from './types.ts';

export function createHelpers(world: World) {
	const seen = { ...world, ...accessHelpers(world) };
	return {
		...seen,
		...shapeHelpers(seen),
		...filterHelpers(seen),
		...jobHelpers(world),
		...accountHelpers(world)
	};
}
export type Helpers = ReturnType<typeof createHelpers>;
