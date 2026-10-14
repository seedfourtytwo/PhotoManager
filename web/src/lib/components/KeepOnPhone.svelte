<script lang="ts">
	/**
	 * "Keep on phone" for an album, a person, a search or the library's filters: for each of
	 * the person's devices, keep it there, leave it off, or neither (FEATURES 10.6).
	 */
	import type { DeviceSync, SyncTarget } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { errorMessage, formatBytes, photos } from '$lib/format';
	import { choiceFor, ruleFor, type Choice } from '$lib/keep';
	import Dialog from './Dialog.svelte';

	type Props = {
		target: SyncTarget;
		/** What is kept, in words: "this album", "Léa", "these photos". */
		what: string;
	};
	let { target, what }: Props = $props();

	const CHOICES: [Choice, string][] = [
		['include', 'Keep on it'],
		['exclude', 'Leave off it'],
		['none', 'Not chosen']
	];
	let open = $state(false);
	let lists = $state<DeviceSync[] | null>(null);
	let error = $state('');
	let busy = $state<number | null>(null);

	async function show() {
		open = true;
		lists = null;
		error = '';
		try {
			const devices = (await api.devices()).filter((d) => !d.revoked);
			lists = await Promise.all(devices.map((d) => api.deviceSync(d.id)));
		} catch (e) {
			error = errorMessage(e, 'Could not load your devices.');
		}
	}

	async function choose(list: DeviceSync, choice: Choice) {
		const id = list.device.id;
		busy = id;
		try {
			const rule = ruleFor(list.rules, target);
			if (choice !== 'none') await api.keepOnDevice(id, { ...target, mode: choice });
			else if (rule) await api.dropFromDevice(id, rule.id);
			const fresh = await api.deviceSync(id);
			lists = (lists ?? []).map((l) => (l.device.id === id ? fresh : l));
		} catch (e) {
			notice.error(e);
		} finally {
			busy = null;
		}
	}
</script>

<button type="button" onclick={show}>Keep on phone</button>

{#if open}
	<Dialog title="Keep on phone" onclose={() => (open = false)} cancelLabel="Done">
		<p class="small intro">
			Choose what each of your phones keeps of {what}. A phone fetches it the next time its Shortcut
			runs. Deleting a photo on the phone does not delete it here.
		</p>
		{#if error}
			<p role="alert">{error}</p>
		{:else if lists === null}
			<p class="quiet">Loading…</p>
		{:else if lists.length === 0}
			<p class="small">
				No phone is set up yet: add one in <a href="/settings#s-devices"
					>Settings → Phones and devices</a
				>.
			</p>
		{:else}
			{#each lists as list (list.device.id)}
				{@const current = choiceFor(list.rules, target)}
				<fieldset disabled={busy === list.device.id}>
					<legend>{list.device.name}</legend>
					{#each CHOICES as [value, label] (value)}
						<label class="choice">
							<input
								type="radio"
								name={`keep-${list.device.id}`}
								{value}
								checked={current === value}
								onchange={() => choose(list, value)}
							/>
							{label}
						</label>
					{/each}
					<p class="quiet small data">{photos(list.count)} · {formatBytes(list.bytes)} in all</p>
				</fieldset>
			{/each}
		{/if}
	</Dialog>
{/if}

<style>
	.intro {
		margin: 0 0 var(--s-3);
		line-height: var(--lh-text);
	}
	fieldset {
		border: 0;
		margin: 0;
		padding: var(--s-2) 0;
		border-top: 1px solid var(--hairline);
	}
	legend {
		padding: var(--s-2) 0 var(--s-1);
	}
	.data {
		margin: var(--s-1) 0 0;
	}
</style>
