const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;

/** Human-readable size, used before downloads ("1,204 photos · 3.2 GB"). Base 1000, like file managers. */
export function formatBytes(bytes: number): string {
	if (!Number.isFinite(bytes) || bytes < 0) throw new RangeError(`invalid byte count: ${bytes}`);
	let value = bytes;
	let unit = 0;
	while (value >= 1000 && unit < UNITS.length - 1) {
		value /= 1000;
		unit += 1;
	}
	const digits = unit === 0 || value >= 100 ? 0 : 1;
	return `${value.toFixed(digits)} ${UNITS[unit]}`;
}

const WHEN = new Intl.DateTimeFormat('en-GB', {
	day: 'numeric',
	month: 'short',
	year: 'numeric',
	hour: '2-digit',
	minute: '2-digit'
});

/** "25 Sept 2026, 02:31" for server timestamps (with or without a zone); '' if unreadable. */
export function formatWhen(iso: string | null | undefined): string {
	if (!iso) return '';
	const ms = Date.parse(iso);
	return Number.isNaN(ms) ? '' : WHEN.format(ms);
}

/**
 * When a folder next checks itself: "next check 9 Oct 2026, 14:00". The server looks for due
 * folders every few minutes, so a moment that has come says that instead; '' when it never does.
 */
export function nextCheckText(iso: string | null | undefined, now: number = Date.now()): string {
	const when = formatWhen(iso);
	if (!when) return '';
	return `next check ${Date.parse(iso!) > now ? when : 'within a few minutes'}`;
}
