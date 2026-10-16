<script lang="ts">
	import { errorMessage } from '$lib/format';
	import { PIN_PROMPTS, enterPin, refusePin, startPin } from '$lib/pin';
	import Dialog from './Dialog.svelte';
	import PinEntry from './PinEntry.svelte';

	/**
	 * Setting a PIN in a sheet, one entry at a time: the current one when it is your own, then
	 * the new one twice (spec flight/admin-settings-auth §4). `submit` is called once, with both
	 * entries the same; a refusal starts over with its reason. Change PIN and Reset PIN.
	 */
	type Props = {
		title: string;
		askCurrent: boolean;
		/** One line under the title (whose PIN, what follows). */
		line?: string;
		submit: (entered: { current: string; pin: string }) => Promise<void>;
		onclose: () => void;
	};
	let { title, askCurrent, line, submit, onclose }: Props = $props();

	// The sheet is made for one purpose: `askCurrent` never changes while it is open.
	const begin = () => startPin(askCurrent);
	let flow = $state(begin());
	let value = $state('');
	let busy = $state(false);

	async function complete(pin: string) {
		if (busy) return;
		const step = enterPin(flow, pin);
		flow = step.flow;
		value = '';
		if (!step.done) return;
		busy = true;
		try {
			await submit(step.done);
			onclose();
		} catch (e) {
			flow = refusePin(flow, errorMessage(e, 'Could not set the PIN.'));
		} finally {
			busy = false;
		}
	}
</script>

<Dialog {title} {onclose}>
	<div class="pin-sheet">
		<p class="prompt" aria-live="polite">{PIN_PROMPTS[flow.step]}</p>
		{#if line}<p class="quiet small">{line}</p>{/if}
		{#key flow.step}
			<PinEntry
				label={PIN_PROMPTS[flow.step]}
				bind:value
				error={flow.error}
				disabled={busy}
				autofocus
				oncomplete={complete}
			/>
		{/key}
	</div>
</Dialog>

<style>
	.pin-sheet {
		display: grid;
		justify-items: center;
		gap: var(--s-2);
		padding-bottom: var(--s-3);
		text-align: center;
	}
	.prompt {
		margin: 0;
		font-size: var(--fs-17);
		font-weight: 600;
	}
	p {
		margin: 0;
	}
</style>
