/** How a backup place and its Proton copy are doing, in the words the admin page uses. */
import type { BackupTarget } from '$lib/api';

export type PlaceState = 'ok' | 'not connected' | 'needs attention';
export type CopyState = 'none' | 'failed' | 'waiting' | 'up to date' | 'first' | 'not made';

/** A failure or an overdue backup needs attention; a place only unplugged is just not connected. */
export function placeState(t: BackupTarget): PlaceState {
	if (t.last_run?.status === 'failed' || t.restore_failing || t.overdue) return 'needs attention';
	return t.last_run?.status === 'skipped' ? 'not connected' : 'ok';
}

/**
 * The Proton copy: waiting when the backup is newer than the copy, or the copy is overdue;
 * "not made" when a backup exists but no copy ever was.
 */
export function protonCopyState(t: BackupTarget): CopyState {
	if (!t.mirror_path) return 'none';
	if (t.mirror_error) return 'failed';
	if (!t.last_mirror_at) return t.last_success_at ? 'not made' : 'first';
	const backupIsNewer = !!t.last_success_at && Date.parse(t.last_success_at) > Date.parse(t.last_mirror_at);
	return t.mirror_overdue || backupIsNewer ? 'waiting' : 'up to date';
} // prettier-ignore

/** The Proton copy is a place too: failed or overdue needs attention, not yet there is not connected. */
export function copyPlaceState(t: BackupTarget): PlaceState {
	if (t.mirror_error || t.mirror_overdue) return 'needs attention';
	return protonCopyState(t) === 'up to date' ? 'ok' : 'not connected';
}
