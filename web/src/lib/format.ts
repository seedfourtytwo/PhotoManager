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
