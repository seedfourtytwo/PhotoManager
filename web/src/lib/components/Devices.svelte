<script lang="ts">
	import type { Device, DevicePlatform } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import { formatWhen } from '$lib/format';
	import Dialog from './Dialog.svelte';

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
			error = e instanceof Error ? e.message : 'Could not add the device.';
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

	async function revoke(device: Device) {
		try {
			await api.revokeDevice(device.id);
			notice.show(`“${device.name}” can no longer upload.`);
			await load();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<section aria-labelledby="s-devices">
	<h2 id="s-devices">Phones and devices</h2>
	<p class="quiet small intro">
		A device token lets a phone send its new photos here on its own (for example with Apple
		Shortcuts while charging). It can only upload, into your own uploads; it cannot see or delete
		anything.
	</p>
	<ul>
		{#each devices ?? [] as device (device.id)}
			<li class:off={device.revoked}>
				<span>{device.name}</span>
				<span class="quiet small">
					{kindLabel(device.platform)} · added {formatWhen(device.created_at)} · {device.last_used_at
						? `last used ${formatWhen(device.last_used_at)}`
						: 'never used'}{#if device.revoked}&nbsp;· revoked{/if}
				</span>
				{#if !device.revoked}
					<button type="button" onclick={() => revoke(device)}>Revoke</button>
				{/if}
			</li>
		{/each}
	</ul>
	<button type="button" class="add" onclick={() => (adding = true)}>Add a device</button>
</section>

{#if adding}
	<Dialog title="Add a device" onclose={close} cancelLabel={token ? 'Done' : 'Cancel'} wide>
		{#if !token}
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
				This token is shown only once. Put it in the phone now; if it is lost, revoke this device
				and add it again.
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
				<code>docs/guides/iphone-shortcut.md</code>.
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
	.intro {
		margin: var(--s-1) 0 var(--s-2);
		line-height: var(--lh-text);
		max-width: var(--measure);
	}
	h3 {
		margin: var(--s-5) 0 var(--s-1);
		font-size: var(--fs-14);
		color: var(--ink);
	}
	ul {
		list-style: none;
		margin: var(--s-2) 0;
		padding: 0;
	}
	li {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		padding: var(--s-2) 0;
		border-bottom: 1px solid var(--hairline);
	}
	li.off span:first-child {
		color: var(--ink-2);
	}
	li button {
		margin-left: auto;
		color: var(--ink-2);
	}
	.add {
		justify-self: start;
		margin-left: calc(-1 * var(--s-2));
		color: var(--ink-2);
	}
	.token {
		font-family: var(--font-mono);
		font-size: var(--fs-12) !important;
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
		display: list-item;
		border: 0;
		padding: var(--s-1) 0;
	}
	.plain {
		list-style: none;
	}
	code {
		font-size: var(--fs-12);
		overflow-wrap: anywhere;
	}
</style>
