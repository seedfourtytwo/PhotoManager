import { describe, expect, it } from 'vitest';
import type { ImportRun, Source } from './api/types';
import { formatWhen } from './format';
import { folderLine, folderNeedsYou } from './folders';

const source = (over: Partial<Source> = {}): Source => ({
	id: 1,
	label: 'Phone',
	path: '/home/c/Phone',
	enabled: true,
	kind: 'folder',
	owner_id: null,
	asset_count: 198,
	problem: null,
	recheck: 'daily',
	next_check_at: null,
	...over
});
const run = (over: Partial<ImportRun> = {}): ImportRun => ({
	id: 9,
	source_id: 1,
	status: 'done',
	started_at: '2026-09-28T21:10:00',
	finished_at: '2026-09-28T21:14:00',
	summary: {
		files_seen: 202,
		imported: 199,
		duplicate: 0,
		skipped: 2,
		failed: 1,
		ignored: 0
	} as ImportRun['summary'],
	message: null,
	...over
});

describe('folderLine: a folder tile in one line', () => {
	it('says how many photos, and what the last import found and when', () => {
		expect(folderLine(source(), run())).toBe(
			`198 photos, last import 199 new, 1 failed, 2 skipped, checked ${formatWhen('2026-09-28T21:14:00')}`
		);
	});
	it('says the count alone before any import', () => {
		expect(folderLine(source({ asset_count: 1 }))).toBe('1 photo');
	});
	it('says an import that is running, with the files seen so far', () => {
		const running = run({ status: 'running', finished_at: null });
		expect(folderLine(source(), running)).toBe('198 photos, importing, 202 files so far');
		expect(
			folderLine(source(), { ...running, summary: { ...running.summary, files_seen: 1 } })
		).toBe('198 photos, importing, 1 file so far');
	});
	it('says why the last import failed', () => {
		expect(folderLine(source(), run({ status: 'failed', message: 'folder not found' }))).toBe(
			'198 photos, last import failed: folder not found'
		);
		expect(folderLine(source(), run({ status: 'failed' }))).toBe(
			'198 photos, last import failed: no reason given'
		);
	});
	it('says a paused folder is paused', () => {
		expect(folderLine(source({ enabled: false }))).toBe('198 photos, paused');
	});
	it('names a run that ended another way, and its message', () => {
		expect(
			folderLine(source(), run({ status: 'paused_low_disk', message: 'the disk is nearly full' }))
		).toBe(
			`198 photos, last import paused_low_disk, 199 new, 1 failed, 2 skipped, checked ${formatWhen('2026-09-28T21:14:00')}, the disk is nearly full`
		);
	});
});

describe('folderNeedsYou: the folder tile gets the red dot', () => {
	it('when the folder has gone or its last import failed', () => {
		expect(folderNeedsYou(source({ problem: 'folder not found' }))).toBe(true);
		expect(folderNeedsYou(source(), run({ status: 'failed' }))).toBe(true);
	});
	it('not for a healthy folder, nor for photos that could not be read', () => {
		expect(folderNeedsYou(source(), run())).toBe(false);
		expect(folderNeedsYou(source())).toBe(false);
	});
});
