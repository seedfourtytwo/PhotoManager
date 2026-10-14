/** The one share that may run at a time, fetching through the app's API client. */
import { photos } from '$lib/format';
import { createSharer, shareOptions, type OptionsFor } from '$lib/share';
import { api } from './api';

export const photoShare = createSharer((id, options) => api.singleDownload(id, options));

/** Each photo in the form the photo view shares it: for a selection, which knows only ids. */
export const formFromDetails: OptionsFor = async (id) => shareOptions(await api.asset(id));

/** Said when the files are here but the sheet needs a fresh tap to open (`ready` in `$lib/share`). */
export const shareAgain = (count: number) =>
	`${count === 1 ? 'The photo is' : 'The photos are'} ready. Tap Share again.`;

/** Said while a selection's files take a moment to come. */
export const gettingPhotos = (count: number) => `Getting ${photos(count)}…`;
