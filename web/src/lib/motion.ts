/**
 * Changes of what is on the page that the eye should be able to follow (spec §4.3): a View
 * Transition where the browser has them, the plain change elsewhere and under reduced motion.
 */
export type Env = {
	start?: (change: () => Promise<void>) => { finished: Promise<void> };
	reduced: boolean;
};

function browser(): Env {
	if (typeof document === 'undefined') return { reduced: true };
	return {
		start: document.startViewTransition
			? (change) => document.startViewTransition(change)
			: undefined,
		reduced: matchMedia('(prefers-reduced-motion: reduce)').matches
	};
}

/** Run `change` as a transition; resolves when it is over. Without one, `change` runs at once. */
export async function withTransition(
	change: () => void | Promise<void>,
	env: Env = browser()
): Promise<void> {
	if (!env.start || env.reduced) {
		await change();
		return;
	}
	// A transition the browser skips or gives up on has still made the change.
	await env
		.start(async () => {
			await change();
		})
		.finished.catch(() => undefined);
}
