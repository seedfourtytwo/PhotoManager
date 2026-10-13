/** Accounts: who is signed in, and wrong PINs as the server counts them. */
import type { IncomingMessage } from 'node:http';
import { randomBytes } from 'node:crypto';
import type { ManagedUser, User } from '../src/lib/api/types.ts';
import { isPin } from '../src/lib/api/types.ts';
import { noWrongPins } from './data.ts';
import { HttpError, idParam, type Ctx } from './http.ts';
import type { MockUser, World } from './types.ts';

export function publicUser(u: MockUser): User {
	return {
		id: u.id,
		username: u.username,
		display_name: u.display_name,
		role: u.role,
		disabled: u.disabled
	};
}

// Wrong PINs, as the server counts them (backend: domain/access.py, app/accounts.py).
const WRONG_PIN_WINDOW = 15 * 60_000;
const MAX_RECENT_WRONG_PINS = 10;
export const LOCK_AFTER_WRONG_PINS = 30;

export function forgiveWrongPins(user: MockUser) {
	Object.assign(user, noWrongPins());
}

export function checkPin(pin: unknown) {
	if (typeof pin !== 'string' || !isPin(pin))
		throw new HttpError(422, 'PINs are exactly 4 digits.');
}

export function accountHelpers(h: World) {
	function startSession(user: MockUser): Record<string, string> {
		const token = randomBytes(18).toString('base64url');
		h.state().sessions.set(token, user.id);
		return {
			'set-cookie': `pa_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000`
		};
	}

	/**
	 * One counted try at an account's PIN: is it right? Counted per account, whatever browser
	 * it comes from, and before the PIN is looked at. Refused while the account is locked (423)
	 * or has ten tries in the last 15 minutes (429); the caller forgives after a right PIN.
	 */
	function tryPin(user: MockUser, pin: string): boolean {
		if (user.locked)
			throw new HttpError(
				423,
				"This account is locked after too many wrong PINs; ask an admin to unlock it, or set a new PIN on the server with 'just set-pin'"
			);
		const recent = wrongPinsInWindow(user);
		if (recent.length >= MAX_RECENT_WRONG_PINS) {
			const minutes = Math.max(1, Math.ceil((recent[0] + WRONG_PIN_WINDOW - h.now()) / 60_000));
			throw new HttpError(
				429,
				`Too many wrong PINs; wait ${minutes} minute${minutes === 1 ? '' : 's'} and try again, or ask an admin to unlock this account`
			);
		}
		user.recentWrongPins = [...recent, h.now()];
		user.failedPins += 1;
		user.locked = user.failedPins >= LOCK_AFTER_WRONG_PINS;
		return user.pin === pin;
	}

	const wrongPinsInWindow = (user: MockUser) =>
		user.recentWrongPins.filter((t) => h.now() - t < WRONG_PIN_WINDOW);

	/** What only admins are told: the lock, or the 15-minute wait, that wrong PINs caused. */
	const managedUser = (u: MockUser): ManagedUser => ({
		...publicUser(u),
		locked: u.locked || wrongPinsInWindow(u).length >= MAX_RECENT_WRONG_PINS
	});

	function accountOf(ctx: Ctx): MockUser {
		const user = h.state().users.find((u) => u.id === idParam(ctx));
		if (!user) throw new HttpError(404, 'no such user');
		return user;
	}

	function sessionUser(req: IncomingMessage): MockUser | null {
		const cookie = req.headers.cookie ?? '';
		const token = /(?:^|;\s*)pa_session=([^;]+)/.exec(cookie)?.[1];
		const userId = token ? h.state().sessions.get(token) : undefined;
		const user = h.state().users.find((u) => u.id === userId);
		return user && !user.disabled ? user : null;
	}

	return { startSession, tryPin, managedUser, accountOf, sessionUser };
}
