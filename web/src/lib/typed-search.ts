import { goto } from '$app/navigation';
import { searchHref } from './search';

/** How long typing must pause before it searches (spec library-search-viewer §5). */
export const TYPING_PAUSE = 250;

/**
 * Search as it is typed: once the typing pauses, the address becomes the search (in place,
 * not a history step per letter); `now` searches at once (Enter). Nothing typed is the page's
 * empty state. `push` makes it a step of its own (a search started from another page).
 */
export function typedSearch() {
	let timer: ReturnType<typeof setTimeout> | undefined;
	return (words: string, { now = false, push = false } = {}) => {
		clearTimeout(timer);
		const go = () => {
			const q = words.trim();
			void goto(q ? searchHref(q) : '/search', {
				replaceState: !push,
				keepFocus: true,
				noScroll: true
			});
		};
		if (now) go();
		else timer = setTimeout(go, TYPING_PAUSE);
	};
}
