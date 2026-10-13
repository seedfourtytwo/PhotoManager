import { describe, expect, it } from 'vitest';
import type { Handover, HandoverOptions, LinkAddress } from './api/types';
import {
	addressLabel,
	clock,
	deviceWord,
	firstChoice,
	outcome,
	stateLine,
	summary,
	unavailable
} from './send';

const HTTPS: LinkAddress = {
	via: 'here',
	origin: 'https://photos.example.ts.net',
	encrypted: true
};
const HOME: LinkAddress = { via: 'home', origin: 'http://192.168.1.20:8421', encrypted: false };
const options = (over: Partial<HandoverOptions> = {}): HandoverOptions => ({
	addresses: [HTTPS, HOME],
	unencrypted_allowed: true,
	remove_details: true,
	minutes: 10,
	max_photos: 100,
	max_bytes: 1e9,
	...over
});
const handover = (over: Partial<Handover> = {}): Handover => ({
	id: 1,
	state: 'waiting',
	count: 3,
	bytes: 8_400_000,
	created_at: '2026-10-13T12:00:00Z',
	expires_at: '2026-10-13T12:10:00Z',
	encrypted: true,
	details_removed: true,
	sent_by: { id: 1, display_name: 'C' },
	redeemed_at: null,
	redeemed_from: null,
	redeemed_agent: null,
	...over
});

describe('where a link can point', () => {
	it('starts on an encrypted address when there is one', () => {
		expect(firstChoice([HOME, HTTPS])).toBe(HTTPS);
		expect(firstChoice([HOME])).toBe(HOME);
		expect(firstChoice([])).toBeNull();
	});

	it('names each address by where the other device is and whether it is encrypted', () => {
		expect(addressLabel(HTTPS)).toBe(
			'Somewhere that reaches this address · encrypted (photos.example.ts.net)'
		);
		expect(addressLabel(HOME)).toBe('On the home Wi-Fi · not encrypted (192.168.1.20:8421)');
	});
});

describe('why nothing can be sent', () => {
	it('is nothing when the chosen address works', () => {
		expect(unavailable(options(), HTTPS, false)).toBeNull();
		expect(unavailable(options(), HOME, false)).toBeNull();
	});

	it('tells an admin the setting and anyone else whom to ask when no address is reachable', () => {
		const none = options({ addresses: [] });
		expect(unavailable(none, null, true)).toContain('PA_SEND_TO_DEVICE_ADDRESS');
		const member = unavailable(none, null, false);
		expect(member).toContain('ask whoever runs the library');
		expect(member).not.toContain('PA_');
	});

	it('says to use the https address when unencrypted sending is switched off', () => {
		const strict = options({ unencrypted_allowed: false });
		expect(unavailable(strict, HOME, false)).toContain('https address');
		expect(unavailable(strict, HTTPS, false)).toBeNull();
	});
});

describe('the words under the code', () => {
	it('sums up what is sent', () => {
		expect(summary(handover())).toBe('3 photos · 8.4 MB · details removed');
		expect(summary(handover({ count: 1, bytes: 900, details_removed: false }))).toBe(
			'1 photo · 900 B · details kept'
		);
	});

	it('counts down in minutes and seconds and stops at zero', () => {
		expect(clock(600_000)).toBe('10:00');
		expect(clock(581_000)).toBe('9:41');
		expect(clock(59_001)).toBe('1:00');
		expect(clock(1)).toBe('0:01');
		expect(clock(0)).toBe('0:00');
		expect(clock(-5000)).toBe('0:00');
	});

	it('has a sentence for every state', () => {
		expect(stateLine('waiting')).toBe('Waiting for the other device…');
		expect(stateLine('redeemed')).toBe('Downloaded on another device.');
		expect(stateLine('expired')).toContain('run out');
		expect(stateLine('cancelled')).toContain('cancelled');
	});
});

describe('the trail', () => {
	it('names a kind of device, never the whole browser string', () => {
		expect(deviceWord('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)')).toBe('an iPhone');
		expect(deviceWord('Mozilla/5.0 (Linux; Android 14; Pixel 7)')).toBe('an Android device');
		expect(deviceWord('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')).toBe('a Mac');
		expect(deviceWord('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('a Windows computer');
		expect(deviceWord('Mozilla/5.0 (X11; Linux x86_64)')).toBe('a Linux computer');
		expect(deviceWord('curl/8.5.0')).toBe('a device');
		expect(deviceWord(null)).toBe('a device');
	});

	it('says what became of a link', () => {
		expect(outcome(handover())).toMatch(/^Waiting until 13 Oct 2026/);
		expect(outcome(handover({ state: 'expired' }))).toBe('Ran out, never downloaded');
		expect(outcome(handover({ state: 'cancelled' }))).toBe('Cancelled');
		const taken = handover({
			state: 'redeemed',
			redeemed_at: '2026-10-13T12:03:00Z',
			redeemed_from: '100.64.0.9',
			redeemed_agent: 'Mozilla/5.0 (iPhone)'
		});
		expect(outcome(taken)).toMatch(/^Downloaded 13 Oct 2026, .* by an iPhone at 100\.64\.0\.9$/);
	});
});
