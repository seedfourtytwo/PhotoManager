import { updated } from '$app/state';
import { reloadIfOutdated } from '$lib/fresh-build';

// A file of this build failed to load: if a newer build replaced it, reload into that one.
window.addEventListener('vite:preloadError', () => {
	void reloadIfOutdated({
		check: () => updated.check(),
		reload: () => location.reload(),
		storage: () => sessionStorage,
		now: Date.now()
	});
});
