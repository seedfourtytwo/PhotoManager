<script lang="ts">
	import type { Device, DevicePlatform } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { errorMessage, formatWhen } from '$lib/format';
	import DeviceKeeps from './DeviceKeeps.svelte';
	import Dialog from './Dialog.svelte';
	import IconButton from './ui/IconButton.svelte';
	import TileGroup from './ui/TileGroup.svelte';
	import TileRow from './ui/TileRow.svelte';

	let devices = $state<Device[] | null>(null);
	let adding = $state(false);
	let name = $state('');
	let platform = $state<DevicePlatform>('ios');
	let token = $state<string | null>(null);
	let copied = $state(false);
	let error = $state('');
	let busy = $state(false);
	const origin = typeof location === 'undefined' ? '' : location.origin;
	const KINDS: [DevicePlatform, string][] = [
		['ios', 'iPhone or iPad'],
		['android', 'Android phone'],
		['desktop', 'Computer'],
		['other', 'Something else']
	];
	const kindLabel = (p: string) => KINDS.find(([k]) => k === p)?.[1] ?? p;
	const used = (device: Device) =>
		device.last_used_at ? `last used ${formatWhen(device.last_used_at)}` : 'never used';

	async function load() {
		try {
			devices = await api.devices();
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => void load());

	async function create() {
		if (busy) return;
		busy = true;
		error = '';
		try {
			const created = await api.createDevice({ name: name.trim(), platform });
			token = created.token;
			await load();
		} catch (e) {
			error = errorMessage(e, 'Could not add the phone.');
		} finally {
			busy = false;
		}
	}

	async function copy() {
		if (!token) return;
		try {
			await navigator.clipboard.writeText(token);
			copied = true;
		} catch {
			notice.show('Copying is blocked here: select the token and copy it by hand.');
		}
	}

	function close() {
		adding = false;
		token = null;
		copied = false;
		name = '';
	}

	/** The phone whose sheet is open: what it keeps, and the way to revoke it. */
	let open = $state<Device | null>(null);
	/** Revoking cannot be undone (the token is shown only once), so it asks first. */
	let revoking = $state<Device | null>(null);

	async function revoke(device: Device) {
		revoking = null;
		try {
			await api.revokeDevice(device.id);
			notice.show(`“${device.name}” can no longer upload.`);
			await load();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<TileGroup label="Phones that send photos here">
	{#snippet action()}
		{#if devices?.length}
			<IconButton icon="plus" label="Add a phone" onclick={() => (adding = true)} />
		{/if}
	{/snippet}
	{#each devices ?? [] as device (device.id)}
		{#if device.revoked}
			<TileRow icon="phone" title={device.name} line="Revoked" />
		{:else}
			<TileRow
				icon="phone"
				title={device.name}
				line={`${kindLabel(device.platform)}, ${used(device)}`}
				onclick={() => (open = device)}
			/>
		{/if}
	{:else}
		{#if devices}
			<TileRow
				icon="plus"
				title="Add a phone"
				line="It sends its new photos here on its own"
				onclick={() => (adding = true)}
			/>
		{/if}
	{/each}
</TileGroup>

{#if revoking}
	{@const device = revoking}
	<Dialog title={`Revoke “${device.name}”?`} onclose={() => (revoking = null)}>
		<p>
			It stops uploading at once. Its token cannot be shown again: to use this phone later, add it
			again and put the new token in it.
		</p>
		{#snippet actions()}
			<button class="primary" type="button" onclick={() => revoke(device)}>Revoke</button>
		{/snippet}
	</Dialog>
{:else if open}
	{@const device = open}
	<Dialog title={device.name} onclose={() => (open = null)} cancelLabel="Close" wide>
		<p class="quiet about">
			{kindLabel(device.platform)}, added {formatWhen(device.created_at)}, {used(device)}
		</p>
		<DeviceKeeps deviceId={device.id} />
		<div class="apart">
			<TileGroup>
				<TileRow
					icon="x"
					title="Revoke"
					line="It can no longer send or fetch photos"
					danger
					onclick={() => {
						revoking = device; // first: `device` follows `open`
						open = null;
					}}
				>
					{#snippet trailing()}{/snippet}
				</TileRow>
			</TileGroup>
		</div>
	</Dialog>
{:else if adding}
	<Dialog title="Add a phone" onclose={close} cancelLabel={token ? 'Done' : 'Cancel'} wide>
		{#if !token}
			<p class="quiet small intro">
				A phone with its own token sends its new photos here (for example with Apple Shortcuts while
				charging) and fetches what you keep on it. It can only upload into your own uploads and
				download what you keep on it; it cannot see anything else or delete anything.
			</p>
			<label class="field">Name <input bind:value={name} placeholder="Léa’s iPhone" /></label>
			<label class="field"
				>Kind
				<select bind:value={platform}>
					{#each KINDS as [value, label] (value)}<option {value}>{label}</option>{/each}
				</select>
			</label>
			{#if error}<p role="alert">{error}</p>{/if}
		{:else}
			<label class="field">
				Device token
				<input class="token" readonly value={token} onfocus={(e) => e.currentTarget.select()} />
			</label>
			<p class="small">
				<button type="button" class="copy" onclick={copy}>Copy</button>
				{#if copied}<span class="quiet" role="status">Copied.</span>{/if}
			</p>
			<p class="small">
				This token is shown only once. Put it in the phone now; if it is lost, revoke this phone and
				add it again.
			</p>
			<h3>iPhone: upload with Shortcuts</h3>
			<ol class="small">
				<li>Shortcuts → Automation → + → Charger → Is Connected → Run Immediately.</li>
				<li>Find Photos: Date Added in the last 2 days, Media Type is Image, limit 50.</li>
				<li>Repeat with Each, and inside it Get Contents of URL:</li>
				<li class="plain">
					<code>POST {origin}/api/upload</code>, header <code>Authorization</code> =
					<code>Bearer</code> + the token, Request Body Form, field <code>file</code> = Repeat Item.
				</li>
			</ol>
			<p class="quiet small">
				The full walk-through, with a safer “only new photos” variant, is in the project's guide
				<code>docs/guides/iphone-shortcut.md</code>. To get albums, people or searches onto the
				phone, see <code>docs/guides/keep-on-my-phone.md</code>.
			</p>
		{/if}
		{#snippet actions()}
			{#if !token}
				<button class="primary" type="button" disabled={busy || !name.trim()} onclick={create}
					>Create</button
				>
			{/if}
		{/snippet}
	</Dialog>
{/if}

<style>
	.about {
		margin: calc(-1 * var(--s-2)) 0 var(--s-4);
	}
	.apart {
		margin-top: var(--s-5);
	}
	.intro {
		margin: 0 0 var(--s-4);
		line-height: var(--lh-text);
	}
	h3 {
		margin: var(--s-5) 0 var(--s-1);
		color: var(--ink);
	}
	.token {
		font-family: var(--font-data);
		font-stretch: 80%;
		font-size: var(--fs-13) !important;
		color: var(--ink);
	}
	.copy {
		margin-left: calc(-1 * var(--s-2));
		text-decoration: underline;
		text-underline-offset: 0.2em;
	}
	p.small {
		margin: var(--s-2) 0;
		line-height: var(--lh-text);
	}
	ol {
		padding-left: var(--s-5);
		margin: var(--s-1) 0;
		line-height: var(--lh-text);
	}
	ol li {
		padding: var(--s-1) 0;
	}
	.plain {
		list-style: none;
	}
	code {
		font-size: var(--fs-13);
		overflow-wrap: anywhere;
	}
</style>
