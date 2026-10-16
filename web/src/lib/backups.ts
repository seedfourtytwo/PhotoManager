/** How a backup place and its Proton copy are doing, in the words the admin page uses. */
import type { BackupErrorKind, BackupHealth, BackupProblem, BackupTarget } from '$lib/api';
import { plural } from './format';

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

/** A problem as people read it: what happened, what to do, and the tool's own text kept aside. */
export type PlainProblem = { headline: string; line: string; details: string | null };

const KIND_WORDS: Record<BackupErrorKind, { headline: string; line: string }> = {
	unreachable: {
		headline: "Backup place didn't answer",
		line: "Check it's switched on and connected, then back up again."
	},
	disk_full: {
		headline: 'Backup place is full',
		line: 'Make space there, or add another backup place.'
	},
	auth: {
		headline: "Backup couldn't unlock",
		line: 'Its password or sign-in was refused. Open Backups to set it again.'
	},
	locked: {
		headline: 'Backup was busy',
		line: 'Another backup was still running. It tries again by itself.'
	},
	unknown: {
		headline: "Last backup didn't finish",
		line: 'Open Backups and press Back up now. Details has what went wrong.'
	}
};

/** The headline and the line of what to do for one kind of failure. */
export function kindWords(kind: BackupErrorKind): { headline: string; line: string } {
	return KIND_WORDS[kind];
}

/**
 * A backup problem in plain words. A failure (it has an `error_kind`) gets its kind's words and
 * keeps the raw text for Details; any other problem (overdue, key not saved) is already a plain
 * sentence from the server, so it is the line under a general headline.
 */
export function problemWords(problem: BackupProblem): PlainProblem {
	if (problem.error_kind) return { ...KIND_WORDS[problem.error_kind], details: problem.message };
	const headline = problem.severity === 'alert' ? 'Backups need you' : 'Backups need a look';
	return { headline, line: problem.message, details: null };
}

/**
 * The one plain sentence on the Backups row: the first problem's headline, else where the
 * library is safe; '' until the health is known.
 */
export function backupSentence(health: BackupHealth | null): string {
	if (!health) return '';
	if (health.problems.length) return problemWords(health.problems[0]).headline;
	if (health.places_total === 0) return 'No backups yet: the library exists only on this computer';
	if (health.protected) return `Protected in ${plural(health.places_ok, 'place')}`;
	return `Only ${health.places_ok} of ${plural(health.places_total, 'place')} up to date`;
}
