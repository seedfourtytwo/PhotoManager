import { describe, expect, it } from 'vitest';
import type { BackupHealth, BackupProblem, BackupTarget } from '$lib/api';
import {
	backupSentence,
	copyPlaceState,
	kindWords,
	placeState,
	problemWords,
	protonCopyState
} from './backups';

const target = (over: Partial<BackupTarget> = {}): BackupTarget =>
	({
		enabled: true,
		overdue: false,
		restore_failing: false,
		last_run: null,
		last_success_at: '2026-10-01T02:30:00',
		mirror_path: '/my-files/Backup',
		last_mirror_at: '2026-10-01T03:00:00',
		mirror_error: null,
		mirror_overdue: false,
		...over
	}) as BackupTarget;
const run = (status: 'succeeded' | 'failed' | 'skipped' | 'running') =>
	({ status }) as BackupTarget['last_run'];

describe('placeState', () => {
	it('is ok for a healthy place, including one never run', () => {
		expect(placeState(target({ last_run: run('succeeded') }))).toBe('ok');
		expect(placeState(target({ last_run: null }))).toBe('ok');
		expect(placeState(target({ last_run: run('running') }))).toBe('ok');
	});
	it('needs attention after a failed run, a failed restore test or when overdue', () => {
		expect(placeState(target({ last_run: run('failed') }))).toBe('needs attention');
		expect(placeState(target({ restore_failing: true }))).toBe('needs attention');
		expect(placeState(target({ overdue: true }))).toBe('needs attention');
	});
	it('is not connected when the latest run was skipped and nothing is overdue', () => {
		expect(placeState(target({ last_run: run('skipped') }))).toBe('not connected');
	});
	it('needs attention when skipped for so long that it is overdue', () => {
		expect(placeState(target({ last_run: run('skipped'), overdue: true }))).toBe('needs attention');
	});
});

describe('protonCopyState', () => {
	it('is none without a Proton folder', () => {
		expect(protonCopyState(target({ mirror_path: null }))).toBe('none');
	});
	it('has failed when the copy reported an error', () => {
		expect(protonCopyState(target({ mirror_error: 'offline' }))).toBe('failed');
	});
	it('is up to date when the copy is newer than the backup', () => {
		expect(protonCopyState(target())).toBe('up to date');
	});
	it('waits to go online when overdue, even if the dates look fine', () => {
		expect(protonCopyState(target({ mirror_overdue: true }))).toBe('waiting');
	});
	it('waits when the backup is newer than the last copy', () => {
		expect(protonCopyState(target({ last_success_at: '2026-10-02T02:30:00' }))).toBe('waiting');
	});
	it('has not made the first copy yet when there is a backup but no copy', () => {
		expect(protonCopyState(target({ last_mirror_at: null }))).toBe('not made');
		expect(protonCopyState(target({ last_mirror_at: null, mirror_overdue: true }))).toBe(
			'not made'
		);
	});
	it('is first copy when there is neither backup nor copy', () => {
		expect(protonCopyState(target({ last_mirror_at: null, last_success_at: null }))).toBe('first');
	});
});

describe('copyPlaceState', () => {
	it('is ok when up to date', () => {
		expect(copyPlaceState(target())).toBe('ok');
	});
	it('needs attention when the copy failed or is overdue', () => {
		expect(copyPlaceState(target({ mirror_error: 'offline' }))).toBe('needs attention');
		expect(copyPlaceState(target({ mirror_overdue: true }))).toBe('needs attention');
	});
	it('is not connected while waiting to go online or not yet made', () => {
		expect(copyPlaceState(target({ last_success_at: '2026-10-02T02:30:00' }))).toBe(
			'not connected'
		);
		expect(copyPlaceState(target({ last_mirror_at: null }))).toBe('not connected');
		expect(copyPlaceState(target({ last_mirror_at: null, last_success_at: null }))).toBe(
			'not connected'
		);
	});
});

describe('backupSentence: the one plain sentence on the Backups tile', () => {
	const health = (over: Partial<BackupHealth> = {}): BackupHealth => ({
		protected: true,
		places_ok: 2,
		places_total: 2,
		problems: [],
		...over
	});
	it('says nothing until the health is known', () => {
		expect(backupSentence(null)).toBe('');
	});
	it("says the first problem in plain words, never the tool's text", () => {
		const problems = [
			{
				severity: 'alert' as const,
				message: 'Home server: the last backup failed',
				target_id: 1,
				error_kind: 'unknown' as const
			},
			{
				severity: 'warning' as const,
				message: 'USB disk: not connected',
				target_id: 2,
				error_kind: 'unreachable' as const
			}
		];
		expect(backupSentence(health({ protected: false, places_ok: 0, problems }))).toBe(
			"Last backup didn't finish"
		);
	});
	it('says where the library is safe', () => {
		expect(backupSentence(health())).toBe('Protected in 2 places');
		expect(backupSentence(health({ places_ok: 1, places_total: 1 }))).toBe('Protected in 1 place');
	});
	it('says how many places are behind, without a problem to name', () => {
		expect(backupSentence(health({ protected: false, places_ok: 1 }))).toBe(
			'Only 1 of 2 places up to date'
		);
	});
	it('says there is no backup at all', () => {
		expect(backupSentence(health({ protected: false, places_ok: 0, places_total: 0 }))).toBe(
			'No backups yet: the library exists only on this computer'
		);
	});
});

describe('problemWords: a headline, one line of what to do, the raw text behind Details', () => {
	const problem = (error_kind: BackupProblem['error_kind'], message = 'raw: tool said no') => ({
		severity: 'alert' as const,
		message,
		target_id: 1,
		error_kind
	});

	it.each([
		['unreachable', "Backup place didn't answer", /switched on/],
		['disk_full', 'Backup place is full', /space/],
		['auth', "Backup couldn't unlock", /password/],
		['locked', 'Backup was busy', /tries again by itself/],
		['unknown', "Last backup didn't finish", /Back up now/]
	] as const)('%s', (kind, headline, line) => {
		const words = problemWords(problem(kind));
		expect(words.headline).toBe(headline);
		expect(words.line).toMatch(line);
		expect(words.details).toBe('raw: tool said no');
	});

	it('keeps every headline short: six words at most', () => {
		for (const kind of ['unreachable', 'disk_full', 'auth', 'locked', 'unknown'] as const)
			expect(kindWords(kind).headline.split(' ').length).toBeLessThanOrEqual(6);
	});

	it('a problem that is no failure (overdue, key not saved) is already plain: it is the line', () => {
		const words = problemWords({
			...problem(null, 'USB disk: the backup is overdue.'),
			severity: 'warning'
		});
		expect(words.headline).toBe('Backups need a look');
		expect(words.line).toBe('USB disk: the backup is overdue.');
		expect(words.details).toBeNull();
	});

	it('an alert that is no failure says it needs you', () => {
		expect(problemWords(problem(null, 'Only 0 of 2 backup places is up to date.')).headline).toBe(
			'Backups need you'
		);
	});
});
