<script lang="ts">
	import type { Access, Level, User } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';

	type Props = { sourceId: number; label: string; onclose: () => void };
	let { sourceId, label, onclose }: Props = $props();

	let access = $state<Access | null>(null);
	let users = $state<User[]>([]);
	let adding = $state('');

	$effect(() => {
		Promise.all([api.sourceAccess(sourceId), api.users()])
			.then(([a, u]) => {
				access = a;
				users = u;
			})
			.catch((e: unknown) => notice.error(e));
	});

	const nameOf = (id: number) => users.find((u) => u.id === id)?.display_name ?? `User ${id}`;
	const levels: [Level, string][] = [
		['view', 'View'],
		['download', 'View + download'],
		['edit', 'Edit']
	];

	async function save() {
		if (!access) return;
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
	{#if access}
		<label class="row">
			Everyone
			<select
				value={access.everyone ?? ''}
				onchange={(e) => (access!.everyone = (e.currentTarget.value || null) as Level | null)}
			>
				<option value="">Nobody (only the people below)</option>
				{#each levels as [value, text] (value)}<option {value}>{text}</option>{/each}
			</select>
		</label>
		{#each access.users as entry, i (entry.user_id)}
			<div class="row">
				<span>{nameOf(entry.user_id)}</span>
				<select
					aria-label={`Access for ${nameOf(entry.user_id)}`}
					bind:value={access.users[i].level}
				>
					{#each levels as [value, text] (value)}<option {value}>{text}</option>{/each}
				</select>
				<button
					type="button"
					onclick={() => (access!.users = access!.users.filter((u) => u.user_id !== entry.user_id))}
					>Remove</button
				>
			</div>
		{/each}
		<div class="row">
			<select bind:value={adding} aria-label="Person to add">
				<option value="">Add a person…</option>
				{#each users.filter((u) => u.role !== 'admin' && !access?.users.some((x) => x.user_id === u.id)) as u (u.id)}
					<option value={String(u.id)}>{u.display_name}</option>
				{/each}
			</select>
			<button
				type="button"
				disabled={!adding}
				onclick={() => {
					access!.users = [...access!.users, { user_id: Number(adding), level: 'view' }];
					adding = '';
				}}>Add</button
			>
		</div>
		<p class="quiet small">
			Admins can always edit. A photo that is also in another folder, or in an album shared with
			someone, stays visible to them there.
		</p>
	{:else}
		<p class="quiet" role="status">Loading…</p>
	{/if}
	{#snippet actions()}
		<button class="primary" type="button" disabled={!access} onclick={save}>Save</button>
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
	.row button {
		color: var(--ink-2);
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
