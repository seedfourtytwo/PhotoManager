/**
 * The API client every module speaks through. What a 401 does is the session's business, and
 * the session needs this client, so it hands its answer in here instead of being imported.
 */
import { createApi } from '$lib/api';

let unauthorized: () => void = () => undefined;

/** Set what any 401 does (the session: forget the user, go to sign-in). */
export function onUnauthorized(run: () => void) {
	unauthorized = run;
}

export const api = createApi({ onUnauthorized: () => unauthorized() });
