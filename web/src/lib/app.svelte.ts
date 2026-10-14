/**
 * App-wide state: the API client, the signed-in user, viewer settings and the status line.
 * Svelte runes in modules, so every component shares one instance. Each subject has its own
 * file in `state/`; this is the one door importers use.
 */
export { api } from './state/api';
export { backupWatch } from './state/backup-watch.svelte';
export { library } from './state/library.svelte';
export { chooseMode, loadLook } from './state/look-loading';
export { notice, type NoticeAction } from './state/notice.svelte';
export { isPublicRoute, session } from './state/session.svelte';
export { formFromDetails, gettingPhotos, photoShare, shareAgain } from './state/share';
export { forgetOldDensity, settings } from './state/settings.svelte';
export { viewport } from './state/ui.svelte';
