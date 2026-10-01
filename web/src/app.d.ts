// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {
		interface PageState {
			/** Shallow-routed loupe: Back closes it. */
			loupe?: number;
		}
	}
}

export {};
