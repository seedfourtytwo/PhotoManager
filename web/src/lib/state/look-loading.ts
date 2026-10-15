/** The account's look: fetching it, and the parts an account sets itself. */
import {
	DEFAULT_LOOK,
	forgetOldMode,
	look,
	oldMode,
	readLook,
	sameLook,
	type HomeSection,
	type Look,
	type Mode,
	type OwnChoice
} from '$lib/look';
import { api } from './api';
import { notice } from './notice.svelte';
import { session } from './session.svelte';

/**
 * Fetch the signed-in account's look and show it: after signing in, and whenever the tab
 * comes back to the foreground (an admin may have changed it meanwhile). Never rejects: with
 * no answer this account's look already on screen stays, and another account's does not.
 * Which answer counts when several requests cross is `look`'s rule ($lib/look/look.svelte).
 *
 * A browser that still holds the old per-device `pa.theme` setting hands it over as the mode,
 * once, and only to an account that has no look yet. The API does not say whether a look was
 * ever stored, so "none yet" is read as "still the defaults": a mode chosen on another
 * device, or a look an admin has set, is never overwritten; the old setting is just dropped.
 */
export async function loadLook(): Promise<void> {
	const user = session.user;
	if (!user) return;
	look.belongsTo(user.id);
	const asked = look.reading();
	try {
		let sheet = await api.myLook();
		const old = oldMode();
		if (old) {
			const untouched = sameLook(readLook(sheet), DEFAULT_LOOK);
			if (untouched && old !== sheet.mode) sheet = await api.setMyMode(old);
			forgetOldMode();
		}
		asked.answer(sheet);
	} catch {
		// offline or refused: asked again the next time the tab comes back
	}
}

/**
 * A part of its look an account sets itself. Shown at once; if it is refused, the screen
 * goes back to what the server last answered, not to an earlier choice still unsaved.
 */
async function chooseOwn(change: OwnChoice, send: () => Promise<Look>): Promise<void> {
	const asked = look.changing({ ...look.saved, ...change });
	try {
		asked.answer(await send());
	} catch (error) {
		asked.fail();
		notice.error(error);
	}
}

/** The account's mode: dark, light or like the device. */
export function chooseMode(mode: Mode): Promise<void> {
	forgetOldMode(); // a choice made here outranks one made before the look moved to the account
	return chooseOwn({ mode }, () => api.setMyMode(mode));
}

/** What the account's Home shows, in order. */
export function chooseHome(sections: HomeSection[]): Promise<void> {
	return chooseOwn({ homeSections: sections }, () => api.setMyHome(sections));
}
