/**
 * "Send to a device": whether this library offers it to the signed-in person, and the photos
 * whose dialog is open. Asked once per person; switched off on the server (404), or for a
 * guest (403), `options` stays null and nothing of the feature is shown anywhere.
 */
import type { HandoverOptions, Id, User } from '$lib/api';
import { api } from './api';

class SendToDevice {
	options = $state<HandoverOptions | null>(null);
	/** The photos of the open dialog, or null while it is closed. */
	sending = $state<Id[] | null>(null);
	#for: Id | null = null;

	get offered(): boolean {
		return this.options !== null;
	}

	/** Who is signed in now (null: nobody). Asks the server once for each person. */
	belongsTo(user: User | null) {
		const id = user && user.role !== 'guest' ? user.id : null;
		if (id === this.#for) return;
		this.#for = id;
		this.options = null;
		this.sending = null;
		if (id === null) return;
		api
			.handoverOptions()
			.then((options) => {
				if (this.#for === id) this.options = options;
			})
			.catch(() => undefined); // off, or not reachable: not offered
	}

	open(ids: Id[]) {
		if (this.offered && ids.length) this.sending = [...ids];
	}

	close() {
		this.sending = null;
	}
}

export const sendToDevice = new SendToDevice();
