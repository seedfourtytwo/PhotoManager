/**
 * A stand-in for the device's share sheet. Chromium on Linux has none, so the Share tests put
 * one in; what a real phone's sheet does is not tested here.
 */
import type { Page } from '@playwright/test';

export type SharedFile = { name: string; type: string; size: number };

/** A share sheet that notes the files it is handed, and opens (or is closed by the person) at once. */
export const withShareSheet = (page: Page, sheet: 'opens' | 'closed' = 'opens') =>
	page.addInitScript((closed) => {
		const seen = window as unknown as { shared: SharedFile[][] };
		seen.shared = [];
		Object.defineProperty(navigator, 'canShare', {
			value: (data?: ShareData) => !!data?.files?.length
		});
		Object.defineProperty(navigator, 'share', {
			value: async (data: ShareData) => {
				seen.shared.push((data.files ?? []).map(({ name, type, size }) => ({ name, type, size })));
				if (closed) throw new DOMException('Share canceled', 'AbortError');
			}
		});
	}, sheet === 'closed');

/** Every call to the sheet so far, each the files it was handed. */
export const shared = (page: Page) =>
	page.evaluate(() => (window as unknown as { shared: SharedFile[][] }).shared);

/** The name a download's answer gives its file. */
export function attachmentName(header: string): string {
	const starred = /filename\*=UTF-8''([^;]+)/.exec(header)?.[1];
	return starred ? decodeURIComponent(starred) : /filename="([^"]+)"/.exec(header)![1];
}
