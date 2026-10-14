<script lang="ts">
	/** One device's "Keep on my phone" list in Settings: what it keeps, what it leaves off,
	 * how big it is and when the device last asked for it (FEATURES 10.6). */
	import type { DeviceSync, Id, SyncRule } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatBytes, formatWhen, photos } from '$lib/format';
	import { SCREENSHOTS, ruleFor, ruleLabel, splitRules, viewOnlyNote } from '$lib/keep';

	let { deviceId }: { deviceId: Id } = $props();
	let sync = $state<DeviceSync | null>(null);
	let busy = $state(false);

	async function load() {
		try {
			sync = await api.deviceSync(deviceId);
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => void load());

	const lastSync = $derived(
		sync?.device.last_sync_at
			? `last synced ${formatWhen(sync.device.last_sync_at)}`
			: 'never synced'
	);
	const groups = $derived(splitRules(sync?.rules ?? []));
	const screenshotsOff = $derived(ruleFor(sync?.rules ?? [], SCREENSHOTS)?.mode === 'exclude');

	async function change(run: () => Promise<unknown>) {
		if (busy) return;
		busy = true;
		try {
			await run();
			await load();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	const drop = (rule: SyncRule) => change(() => api.dropFromDevice(deviceId, rule.id));

	function toggleScreenshots() {
		const rule = ruleFor(sync?.rules ?? [], SCREENSHOTS);
		return change(() =>
			screenshotsOff && rule
				? api.dropFromDevice(deviceId, rule.id)
				: api.keepOnDevice(deviceId, { ...SCREENSHOTS, mode: 'exclude' })
		);
	}

	const resend = () =>
		change(async () => {
			const { forgotten } = await api.resendToDevice(deviceId);
			notice.show(`${photos(forgotten)} will be sent again.`);
		});
</script>

{#if sync}
	<div class="keeps" aria-label={`What ${sync.device.name} keeps`} role="group">
		{#if !sync.rules.length}
			<p class="quiet small">
				Keeps nothing yet. Choose Keep on phone on an album, a person, a search or the library's
				filters.
			</p>
		{/if}
		{#each [{ title: 'Keeps', rules: groups.keeps }, { title: 'Leaves off', rules: groups.leavesOff }] as group (group.title)}
			{#if group.rules.length}
				<h3>{group.title}</h3>
				<ul>
					{#each group.rules as rule (rule.id)}
						<li>
							<span class:quiet={rule.gone}>{ruleLabel(rule)}</span>
							<span class="quiet small data">{photos(rule.count)}</span>
							<button
								type="button"
								disabled={busy}
								aria-label={`Remove ${ruleLabel(rule)}`}
								onclick={() => drop(rule)}>Remove</button
							>
							{#if viewOnlyNote(rule)}<p class="small note">{viewOnlyNote(rule)}</p>{/if}
						</li>
					{/each}
				</ul>
			{/if}
		{/each}
		<p class="quiet small data">
			{photos(sync.count)} · {formatBytes(sync.bytes)} · {sync.sent} sent · {lastSync}
		</p>
		<div class="tools">
			<label class="choice small">
				<input
					type="checkbox"
					checked={screenshotsOff}
					disabled={busy}
					onchange={toggleScreenshots}
				/>
				Leave out screenshots
			</label>
			<button type="button" disabled={busy || !sync.sent} onclick={resend}
				>Send everything again</button
			>
		</div>
	</div>
{/if}

<style>
	.keeps {
		flex-basis: 100%;
		padding-left: var(--s-4);
	}
	h3 {
		margin: var(--s-2) 0 0;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		padding: var(--s-1) 0;
	}
	.note {
		flex-basis: 100%;
		margin: 0;
	}
	li button {
		margin-left: auto;
		color: var(--ink-2);
	}
	p {
		margin: var(--s-1) 0;
	}
	.tools {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--s-1) var(--s-4);
	}
	.tools button {
		color: var(--ink-2);
	}
</style>
