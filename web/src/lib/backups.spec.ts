import { describe, expect, it } from 'vitest';
import type { BackupTarget } from '$lib/api';
import { placeState, protonCopyState } from './backups';

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
	it('waits when there is a backup but no copy yet', () => {
		expect(protonCopyState(target({ last_mirror_at: null }))).toBe('waiting');
	});
	it('is first copy when there is neither backup nor copy', () => {
		expect(protonCopyState(target({ last_mirror_at: null, last_success_at: null }))).toBe('first');
	});
});
