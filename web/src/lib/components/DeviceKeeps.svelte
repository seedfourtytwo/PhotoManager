<script lang="ts">
	/** One phone's "Keep on my phone" list, in its sheet on You: what it keeps, what it leaves
	 * off, how big it is and when the phone last asked for it (FEATURES 10.6). */
	import type { DeviceSync, Id, SyncRule } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatBytes, formatWhen, photos } from '$lib/format';
	import { SCREENSHOTS, ruleFor, ruleLabel, splitRules, viewOnlyNote } from '$lib/keep';
	import IconButton from './ui/IconButton.svelte';
	import TileGroup from './ui/TileGroup.svelte';
	import TileRow from './ui/TileRow.svelte';

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
	<div aria-label={`What ${sync.device.name} keeps`} role="group">
		<p class="quiet data">
			{photos(sync.count)}, {formatBytes(sync.bytes)}, {sync.sent} sent, {lastSync}
		</p>
		{#if !sync.rules.length}
			<p class="quiet">
				Keeps nothing yet. Choose Keep on phone on an album, a person, a search or the library's
				filters.
			</p>
		{/if}
		{#each [{ title: 'Keeps', rules: groups.keeps }, { title: 'Leaves off', rules: groups.leavesOff }] as group (group.title)}
			{#if group.rules.length}
				<TileGroup label={group.title}>
					{#each group.rules as rule (rule.id)}
						<TileRow
							title={ruleLabel(rule)}
							line={viewOnlyNote(rule) ?? undefined}
							value={photos(rule.count)}
						>
							{#snippet trailing()}
								<IconButton
									icon="x"
									label={`Remove ${ruleLabel(rule)}`}
									disabled={busy}
									onclick={() => drop(rule)}
								/>
							{/snippet}
						</TileRow>
					{/each}
				</TileGroup>
			{/if}
		{/each}
		<div class="apart">
			<TileGroup>
				<label class="tile-row">
					<span class="tile-main"><span class="tile-title">Leave out screenshots</span></span>
					<input
						type="checkbox"
						role="switch"
						checked={screenshotsOff}
						disabled={busy}
						onchange={toggleScreenshots}
					/>
				</label>
				{#if sync.sent}
					<TileRow
						icon="refresh"
						title="Send everything again"
						line="The next sync sends every kept photo again"
						onclick={resend}
					>
						{#snippet trailing()}{/snippet}
					</TileRow>
				{/if}
			</TileGroup>
		</div>
	</div>
{/if}

<style>
	p {
		margin: 0 0 var(--s-2);
	}
	.apart {
		margin-top: var(--s-5);
	}
</style>
