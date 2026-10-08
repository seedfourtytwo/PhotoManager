<script lang="ts">
	import type { Access, Level, User } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';
	import PeopleEditor from '../PeopleEditor.svelte';

	type Props = { sourceId: number; label: string; onclose: () => void };
	let { sourceId, label, onclose }: Props = $props();

	// null until the current access is in: Save replaces the whole list.
	let people = $state<{ user_id: number; role: Level }[] | null>(null);
	let everyone = $state<Level | null>(null);
	let users = $state<User[]>([]);

	$effect(() => {
		Promise.all([api.sourceAccess(sourceId), api.users()])
			.then(([a, u]) => {
				everyone = a.everyone;
				people = a.users.map((entry) => ({ user_id: entry.user_id, role: entry.level }));
				users = u;
			})
			.catch((e: unknown) => notice.error(e));
	});

	const levels: [Level, string][] = [
		['view', 'View'],
		['download', 'View + download'],
		['edit', 'Edit']
	];

	async function save() {
		if (!people) return;
		const access: Access = {
			everyone,
			users: people.map((p) => ({ user_id: p.user_id, level: p.role }))
		};
		try {
			await api.setSourceAccess(sourceId, access);
			notice.show('Access saved.');
			onclose();
		} catch (e) {
			notice.error(e);
		}
	}
</script>

<Dialog title={`Who sees “${label}”`} {onclose} wide>
	{#if people}
		<label class="row">
			Everyone
			<select
				value={everyone ?? ''}
				onchange={(e) => (everyone = (e.currentTarget.value || null) as Level | null)}
			>
				<option value="">Nobody (only the people below)</option>
				{#each levels as [value, text] (value)}<option {value}>{text}</option>{/each}
			</select>
		</label>
		<PeopleEditor
			bind:people
			roles={levels}
			roleWord="Access"
			{users}
			addable={users.filter((u) => u.role !== 'admin')}
		/>
		<p class="quiet small">
			Admins can always edit. A photo that is also in another folder, or in an album shared with
			someone, stays visible to them there.
		</p>
	{:else}
		<p class="quiet" role="status">Loading…</p>
	{/if}
	{#snippet actions()}
		<button class="primary" type="button" disabled={!people} onclick={save}>Save</button>
	{/snippet}
</Dialog>

<style>
	.row {
		display: grid;
		grid-template-columns: 8rem 1fr auto;
		align-items: center;
		gap: var(--s-3);
		margin: var(--s-1) 0;
		color: var(--ink);
	}
	p {
		margin: var(--s-3) 0 0;
	}
	@media (max-width: 639px) {
		.row {
			grid-template-columns: 1fr auto;
		}
		.row > :first-child {
			grid-column: 1 / -1;
		}
	}
</style>
