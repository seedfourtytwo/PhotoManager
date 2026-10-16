<script lang="ts">
	import type { Person } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from './Dialog.svelte';

	/** Give someone a name, or change it: from People's "Add name" and from the person's page. */
	type Props = { person: Person; onclose: () => void; onsaved: (person: Person) => void };
	let { person, onclose, onsaved }: Props = $props();

	// svelte-ignore state_referenced_locally (the field starts from the name it opened on)
	let name = $state(person.name ?? '');
	let busy = $state(false);

	async function save(event: SubmitEvent) {
		event.preventDefault();
		if (busy) return;
		busy = true;
		try {
			onsaved(await api.renamePerson(person.id, name.trim() || null));
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Name this person" {onclose}>
	<form id="name-person" onsubmit={save}>
		<label class="field">Name <input bind:value={name} autocomplete="off" /></label>
		<p class="quiet small">Everyone who can see these photos sees this name.</p>
	</form>
	{#snippet actions()}
		<button class="primary" type="submit" form="name-person" disabled={busy}>Save</button>
	{/snippet}
</Dialog>
