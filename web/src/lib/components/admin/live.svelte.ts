/**
 * What the admin sections of Settings watch together: the library's counts and jobs, failed
 * and waiting jobs, and the backup places. One poll for all of them, kept by the Settings
 * layout while any section is open, so moving from Overview to Folders asks nothing again.
 */
import { getContext, setContext } from 'svelte';
import type { BackupTarget, Job, Stats } from '$lib/api';
import { api, backupWatch, library, notice } from '$lib/app.svelte';
import { Poller } from '$lib/poller';

export class AdminLive {
	stats = $state<Stats | null>(null);
	failed = $state<Job[]>([]);
	/** Failed once and waiting for their next attempt: shown with its time, nothing to press. */
	retrying = $state<Job[]>([]);
	backups = $state<BackupTarget[]>([]);
	/** Goes up while work runs, so the folders' import progress follows. */
	refresh = $state(0);

	active = $derived(this.stats ? this.stats.jobs.queued + this.stats.jobs.running : 0);
	backingUp = $derived(this.backups.some((b) => b.last_run?.status === 'running'));

	#started = false;
	/**
	 * Poll while work is queued or running: counts, failed jobs, the folders' live import
	 * progress and backup runs all follow; a finished batch refreshes the library's counts.
	 */
	#poller = new Poller(
		() =>
			Promise.all([
				api.stats(),
				api.jobs('failed'),
				api.backups().catch(() => []),
				api.jobs('waiting'),
				backupWatch.load()
			]),
		(answer) => {
			const wasActive = this.active > 0 || this.backingUp;
			[this.stats, this.failed, this.backups, this.retrying] = answer;
			if (this.active > 0 || wasActive) this.refresh++;
			if (wasActive && this.active === 0) library.changed();
			// a job waiting for its retry will run: keep looking until it has
			return this.active > 0 || this.backingUp || this.retrying.length > 0;
		},
		{ every: 1500, onerror: (e) => notice.error(e) }
	);

	/** Ask now (after a change made here). */
	poll = () => this.#poller.now();

	/** A section that shows any of it starts the watch; it is started once. */
	start() {
		if (this.#started) return;
		this.#started = true;
		void this.poll();
	}

	stop() {
		this.#poller.stop();
	}
}

const KEY = Symbol('admin-live');
export const provideAdminLive = (live: AdminLive) => setContext(KEY, live);
/** The Settings layout's watch; a section that needs it calls `start()`. */
export const adminLive = () => getContext<AdminLive>(KEY);
