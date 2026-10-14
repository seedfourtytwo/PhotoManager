/** What an admin reads on a folder's tile, before opening it. */
import type { ImportRun, Source } from './api/types';
import { formatCount, formatWhen, photos, plural } from './format';

/** The last import in words: running, failed and why, or what it found and when it ended. */
function runText(run: ImportRun): string {
	if (run.status === 'running')
		return `importing · ${plural(run.summary.files_seen, 'file')} so far`;
	if (run.status === 'failed') return `last import failed: ${run.message ?? 'no reason given'}`;
	const { imported, failed, skipped } = run.summary;
	const found = [
		`${formatCount(imported)} new`,
		failed && `${formatCount(failed)} failed`,
		skipped && `${formatCount(skipped)} skipped`
	]
		.filter(Boolean)
		.join(', ');
	return [
		run.status === 'done' ? `last import ${found}` : `last import ${run.status} · ${found}`,
		run.finished_at && `checked ${formatWhen(run.finished_at)}`,
		run.message
	]
		.filter(Boolean)
		.join(' · ');
}

/** "198 photos · last import 6 new, 1 failed · checked 28 Sept 2026, 21:14", "198 photos · paused". */
export function folderLine(source: Source, run?: ImportRun): string {
	return [photos(source.asset_count), !source.enabled && 'paused', run && runText(run)]
		.filter(Boolean)
		.join(' · ');
}

/** The folder has gone, or its last import failed: its tile gets the red dot. */
export function folderNeedsYou(source: Source, run?: ImportRun): boolean {
	return !!source.problem || run?.status === 'failed';
}
