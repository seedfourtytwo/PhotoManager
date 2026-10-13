// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	namespace App {
		interface PageState {
			/** Shallow-routed loupe (lib/loupe.svelte.ts): the open photo, null once closed. */
			photo?: number | null;
			/** This entry was pushed to open the loupe: Back closes it. */
			pushed?: boolean;
			/** This entry is the history step of an open sheet (lib/history-step.ts): its mark. */
			sheet?: string;
			/** This entry is the step of the photo's Info sheet on a phone (lib/info-sheet.svelte.ts). */
			info?: true;
		}
	}
}

export {};
