import { untrack } from 'svelte';
import { library } from './app.svelte';

/**
 * Counts a filter sheet lists, loaded while it is open: again when `key` changes (the other
 * filters did) and after every change to the library, never for a choice of its own. The last
 * answer stays while the next one loads, so the rows do not jump. Created in a component.
 */
export class Counts<T> {
	value = $state.raw<T | null>(null);

	constructor(key: () => string, load: () => Promise<T>) {
		$effect(() => {
			void key();
			void library.version;
			let stale = false;
			untrack(load)
				.then((value) => {
					if (!stale) this.value = value;
				})
				// A count that cannot be had leaves the rows without one; choosing still works.
				.catch(() => undefined);
			return () => (stale = true);
		});
	}
}
