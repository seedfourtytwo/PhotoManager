/** Cursor paging for lists that are read to the end (the map's located photos). */

type CursorPage<T> = { items: T[]; next_cursor: string | null };

/**
 * Walk every page, handing each one over as it arrives so the view fills in while the rest
 * loads. Stops quietly once `isStale()`; a failed page rejects, keeping what was handed over.
 */
export async function eachPage<T>(
	fetchPage: (cursor: string | null) => Promise<CursorPage<T>>,
	onpage: (items: T[]) => void,
	isStale: () => boolean = () => false
): Promise<void> {
	let cursor: string | null = null;
	do {
		const page = await fetchPage(cursor);
		if (isStale()) return;
		onpage(page.items);
		cursor = page.next_cursor;
	} while (cursor && !isStale());
}
