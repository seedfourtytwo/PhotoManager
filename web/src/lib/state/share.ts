/** The one share that may run at a time, fetching through the app's API client. */
import { createSharer } from '$lib/share';
import { api } from './api';

export const photoShare = createSharer((id, options) => api.singleDownload(id, options));

/** Said when the file is here but the sheet needs a fresh tap to open (`ready` in `$lib/share`). */
export const SHARE_AGAIN = 'The photo is ready. Tap Share again.';
