<script lang="ts">
	import { onDestroy, untrack } from 'svelte';
	import type { HandoverOptions, Id, LinkAddress, NewHandover } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { errorMessage, photos } from '$lib/format';
	import { Poller } from '$lib/poller';
	import { encode, svgPath } from '$lib/qr';
	import {
		UNENCRYPTED_WARNING,
		addressLabel,
		clock,
		firstChoice,
		stateLine,
		summary,
		unavailable
	} from '$lib/send';
	import Dialog from './Dialog.svelte';

	type Props = { ids: Id[]; options: HandoverOptions; onclose: () => void };
	let { ids, options, onclose }: Props = $props();

	const POLL_MS = 2000;
	// what the dialog opens on; the person changes both from there
	let chosen = $state<LinkAddress | null>(untrack(() => firstChoice(options.addresses)));
	let removeDetails = $state(untrack(() => options.remove_details));
	let sent = $state<NewHandover | null>(null);
	let status = $state<NewHandover['state']>('waiting');
	let left = $state(0);
	let busy = $state(false);
	let error = $state('');
	let copied = $state(false);
	let watch: Poller<NewHandover['state']> | undefined;
	let ticking: ReturnType<typeof setInterval> | undefined;

	const blocked = $derived(unavailable(options, chosen, session.isAdmin));
	const unencrypted = $derived(chosen !== null && !chosen.encrypted);
	const code = $derived(sent ? svgPath(encode(sent.url)) : null);
	const waiting = $derived(sent !== null && status === 'waiting');

	async function send() {
		if (busy || !chosen || blocked) return;
		busy = true;
		error = '';
		try {
			const made = await api.createHandover({
				ids,
				via: chosen.via,
				remove_details: removeDetails,
				// this click is the yes: the warning is on screen above the button
				unencrypted_ok: unencrypted
			});
			status = made.state;
			sent = made;
			follow(made);
		} catch (e) {
			error = errorMessage(e, 'Could not make the link.');
		} finally {
			busy = false;
		}
	}

	/** Count down by the link's own length (not this device's clock) and ask how it stands. */
	function follow(made: NewHandover) {
		const life = Date.parse(made.expires_at) - Date.parse(made.created_at);
		const until = Date.now() + life;
		left = life;
		ticking = setInterval(() => {
			left = until - Date.now();
			if (left <= 0) clearInterval(ticking);
		}, 1000);
		watch = new Poller(
			() => api.handover(made.id).then((h) => h.state),
			(now) => {
				status = now;
				if (now !== 'waiting') clearInterval(ticking);
				return now === 'waiting';
			},
			{ every: POLL_MS }
		);
		void watch.now();
	}

	function stop() {
		watch?.stop();
		clearInterval(ticking);
	}
	onDestroy(stop);

	/** Closing while the link still waits cancels it: it lives only as long as this is open. */
	function close() {
		stop();
		if (sent && status === 'waiting') {
			void api
				.cancelHandover(sent.id)
				.then(() => notice.show('The link was cancelled.'))
				.catch(() => undefined); // collected or run out meanwhile: nothing to cancel
		}
		onclose();
	}

	async function copy() {
		if (!sent) return;
		try {
			await navigator.clipboard.writeText(sent.url);
			copied = true;
		} catch {
			notice.show('Copying is blocked here: select the link and copy it by hand.');
		}
	}
</script>

<Dialog title="Send to a device" onclose={close} cancelLabel={sent && !waiting ? 'Done' : 'Cancel'}>
	{#if !sent}
		<p class="lead">
			{photos(ids.length)}. The other device opens a link or scans a code and downloads
			{ids.length === 1 ? 'it' : 'them'}, once, within {options.minutes} minutes. It needs no account.
		</p>
		{#if options.addresses.length > 1}
			<fieldset>
				<legend>Where is the other device?</legend>
				{#each options.addresses as address (address.via)}
					<label class="choice">
						<input type="radio" name="via" value={address} bind:group={chosen} />
						{addressLabel(address)}
					</label>
				{/each}
			</fieldset>
		{/if}
		{#if blocked}
			<p class="blocked" role="note">{blocked}</p>
		{:else}
			<label class="choice">
				<input type="checkbox" bind:checked={removeDetails} />
				Remove details before sending
			</label>
			<p class="quiet small hint">
				{removeDetails
					? 'The copies carry no location, no camera details and no file names. Your photos stay as they are.'
					: 'The copies keep their location, camera details and file names.'}
			</p>
			{#if unencrypted}
				<p class="warning" role="note"><strong>Not encrypted.</strong> {UNENCRYPTED_WARNING}</p>
			{/if}
		{/if}
		{#if error}<p role="alert">{error}</p>{/if}
	{:else}
		{#if waiting && code}
			<svg class="code" viewBox={code.viewBox} role="img" aria-label="QR code of the link">
				<rect width="100%" height="100%" fill="#fff" />
				<path d={code.path} fill="#000" />
			</svg>
			<label class="field">
				Link
				<input class="link" readonly value={sent.url} onfocus={(e) => e.currentTarget.select()} />
			</label>
			<p class="small">
				<button type="button" class="copy" onclick={copy}>Copy</button>
				{#if copied}<span class="quiet" role="status">Copied.</span>{/if}
			</p>
		{/if}
		<p class="small data">{summary(sent)}</p>
		{#if !sent.encrypted}<p class="small quiet">Not encrypted.</p>{/if}
		<p class="state" role="status">
			{stateLine(left <= 0 && status === 'waiting' ? 'expired' : status)}
			{#if waiting && left > 0}<span class="quiet data">Works for {clock(left)} more.</span>{/if}
		</p>
		{#if waiting}
			<p class="quiet small">Whoever opens the link first gets the photos. Cancel stops it.</p>
		{/if}
	{/if}
	{#snippet actions()}
		{#if !sent && !blocked}
			<button class="primary" type="button" disabled={busy} onclick={send}
				>{unencrypted ? 'Send anyway' : 'Show the code'}</button
			>
		{/if}
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
		line-height: var(--lh-text);
	}
	.lead {
		max-width: var(--measure);
	}
	fieldset {
		margin: 0 0 var(--s-3);
	}
	/* one choice to a line: each is a sentence, and an address must be able to wrap */
	.choice {
		display: flex;
		margin-right: 0;
		overflow-wrap: anywhere;
	}
	.hint {
		margin-top: calc(-1 * var(--s-1));
	}
	.warning,
	.blocked {
		border-left: 3px solid var(--accent);
		padding: var(--s-2) var(--s-3);
		background: var(--tint);
		border-radius: 0 var(--r-1) var(--r-1) 0;
	}
	.code {
		display: block;
		width: min(16rem, 100%);
		height: auto;
		margin: 0 auto var(--s-4);
		border-radius: var(--r-1);
		/* crisp squares at any size */
		shape-rendering: crispEdges;
	}
	.link {
		width: 100%;
		font-family: var(--font-data);
		font-stretch: 80%;
		font-size: var(--fs-12) !important;
	}
	.copy {
		margin-left: calc(-1 * var(--s-2));
		text-decoration: underline;
		text-underline-offset: 0.2em;
	}
	.state {
		display: flex;
		flex-wrap: wrap;
		gap: var(--s-1) var(--s-3);
		align-items: baseline;
		font-weight: 600;
	}
	.state span {
		font-weight: 400;
	}
</style>
