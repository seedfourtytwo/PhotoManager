/**
 * What a photo is called (backend domain/display_name.py, mirrored for the mock): its minute,
 * numbered ` · 2`… among the photos one sees in that minute; a photo whose date is the file's
 * mtime keeps its file name, tidied, or is `Photo <id>`.
 */
import type { MockAsset } from './types.ts';

const COPY_MARK =
	/(?:\s*\(\s*copy(?:\s+\d+)?\s*\)|\s+-\s+copy(?:\s*\(\d+\))?|\s+copy(?:\s+\d+)?|\s*\(\d+\))$/i;
const FACEBOOK = /^\d+(?:_\d+)+_[a-z]$/;
// eslint-disable-next-line no-control-regex
const UNSAFE = /[\x00-\x1f\x7f/\\:*?"<>|]/g;

function tidy(path: string): string | null {
	const name = (path.split('/').pop() ?? '').normalize('NFC').trim();
	if (name.startsWith('.')) return null;
	let stem = name.replace(/\.[^.]*$/, '');
	let shorter = stem.replace(COPY_MARK, '');
	while (shorter !== stem) {
		stem = shorter;
		shorter = stem.replace(COPY_MARK, '');
	}
	stem = stem.replace(UNSAFE, '_').replace(/^[ .]+|[ .]+$/g, '');
	return /\p{L}/u.test(stem) && !FACEBOOK.test(stem) ? stem : null;
}

const minute = (a: MockAsset) =>
	`${a.taken_at.slice(0, 10)} ${a.taken_at.slice(11, 13)}.${a.taken_at.slice(14, 16)}`;
const before = (x: MockAsset, y: MockAsset) =>
	x.taken_at < y.taken_at || (x.taken_at === y.taken_at && x.id < y.id);

/** `seen`: the photos in the library the viewer sees. */
export function displayName(a: MockAsset, seen: MockAsset[]): string {
	if (a.date_source === 'file_mtime')
		return tidy(a.sources[0]?.relative_path ?? '') ?? `Photo ${a.id}`;
	const earlier = seen.filter(
		(m) =>
			m.id !== a.id && m.date_source !== 'file_mtime' && minute(m) === minute(a) && before(m, a)
	).length;
	return earlier ? `${minute(a)} · ${earlier + 1}` : minute(a);
}
