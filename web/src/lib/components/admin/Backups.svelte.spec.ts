import { page } from 'vitest/browser';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { BackupHealth, BackupRun, BackupTarget } from '$lib/api';
import { api } from '$lib/app.svelte';
import Backups from './Backups.svelte';

afterEach(() => vi.restoreAllMocks());

const run = (over: Partial<BackupRun> = {}): BackupRun => ({
	id: 1,
	kind: 'backup',
	status: 'succeeded',
	started_at: '2026-10-01T02:30:00',
	finished_at: '2026-10-01T02:31:00',
	snapshot_id: null,
	bytes_added: 1000,
	files_new: 1,
	repo_bytes: 5000,
	error: null,
	details: null,
	...over
});
const target = (over: Partial<BackupTarget> = {}): BackupTarget => ({
	id: 1,
	label: 'USB disk',
	kind: 'local',
	repository: '/media/c/USB disk/photos',
	schedule: 'daily 02:30',
	quiet_window: null,
	retention: {},
	enabled: true,
	last_success_at: '2026-10-01T02:31:00',
	last_run: run(),
	repo_bytes: 5000,
	next_run_at: null,
	overdue: false,
	last_proven_at: '2026-10-01T02:32:00',
	restore_failing: false,
	key_saved: true,
	mirror_path: null,
	last_mirror_at: null,
	mirror_error: null,
	needs_attention: false,
	skipped_since: null,
	mirror_overdue: false,
	...over
});
const health = (places_ok: number, places_total: number): BackupHealth => ({
	protected: places_ok >= 2,
	places_ok,
	places_total,
	problems: []
});
const props = (targets: BackupTarget[], h: BackupHealth | null = null) => ({
	targets,
	health: h,
	onchange: () => {}
});
const withCopy = (over: Partial<BackupTarget>) =>
	target({
		mirror_path: '/my-files/Backup',
		last_mirror_at: '2026-10-01T03:00:00',
		...over
	});

describe('Backups header line', () => {
	it('says when two places are protected', async () => {
		render(Backups, props([target()], health(2, 2)));
		await expect.element(page.getByText('Protected in 2 places')).toBeVisible();
	});
	it('says how many places are up to date when fewer than two are', async () => {
		render(Backups, props([target()], health(1, 2)));
		await expect.element(page.getByText('Only 1 of 2 places up to date')).toBeVisible();
	});
	it('says nothing when there are no places', async () => {
		render(Backups, props([], health(0, 0)));
		expect(page.getByText(/places up to date|Protected in/).elements()).toHaveLength(0);
	});
});

describe('a place that is not connected', () => {
	const skipped = target({
		last_run: run({ status: 'skipped', error: 'the disk is not connected' }),
		skipped_since: '2026-09-30T02:30:00'
	});

	it('says since when, and wears the not connected dot', async () => {
		render(Backups, props([skipped]));
		await expect.element(page.getByText(/not connected since 30 Sept? 2026/)).toBeVisible();
		await expect.element(page.getByRole('img', { name: 'not connected' })).toBeVisible();
	});

	it('lists a skipped run with the word skipped', async () => {
		vi.spyOn(api, 'backupRuns').mockResolvedValue([
			run({ id: 2, status: 'skipped', error: 'the disk is not connected' })
		]);
		render(Backups, props([skipped]));
		await page.getByRole('button', { name: 'Recent runs' }).click();
		await expect
			.element(page.getByRole('cell', { name: 'skipped: the disk is not connected' }))
			.toBeVisible();
	});
});

describe('the Proton Drive copy row', () => {
	it('is up to date', async () => {
		render(Backups, props([withCopy({})]));
		await expect
			.element(page.getByText(/Copy on Proton Drive · My files \/ Backup · up to date 1 Oct 2026/))
			.toBeVisible();
		expect(page.getByRole('img', { name: 'ok' }).elements()).toHaveLength(2);
	});
	it('waits to go online', async () => {
		render(Backups, props([withCopy({ last_success_at: '2026-10-02T02:30:00' })]));
		await expect.element(page.getByText(/· waiting to go online/)).toBeVisible();
		await expect.element(page.getByRole('img', { name: 'not connected' })).toBeVisible();
	});
	it('failed, with its reason', async () => {
		render(Backups, props([withCopy({ mirror_error: 'sign in again' })]));
		await expect.element(page.getByText(/· failed: sign in again/)).toBeVisible();
		await expect.element(page.getByRole('img', { name: 'needs attention' })).toBeVisible();
	});
	it('is the first copy, after the next backup', async () => {
		render(
			Backups,
			props([withCopy({ last_mirror_at: null, last_success_at: null, last_run: null })])
		);
		await expect.element(page.getByText(/· first copy after the next backup/)).toBeVisible();
	});
	it('says the first copy is not made yet once a backup exists', async () => {
		render(Backups, props([withCopy({ last_mirror_at: null })]));
		await expect.element(page.getByText(/· first copy not made yet/)).toBeVisible();
	});
});
