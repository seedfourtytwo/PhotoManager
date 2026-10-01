<script lang="ts">
	import type { AlbumMember, User } from '$lib/api';
	import { ApiError } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import Dialog from './Dialog.svelte';

	type Props = { albumId: number; ownerId: number; onclose: () => void };
	let { albumId, ownerId, onclose }: Props = $props();

	let members = $state<AlbumMember[]>([]);
	let users = $state<User[] | null>(null);
	let adding = $state('');
	let busy = $state(false);

	$effect(() => {
		api
			.albumMembers(albumId)
			.then((m) => (members = m))
			.catch((e: unknown) => notice.error(e));
		// The contract only lists users for admins; others add people by user id.
		api
			.users()
			.then((u) => (users = u))
			.catch((e: unknown) => {
				if (!(e instanceof ApiError && e.status === 403)) notice.error(e);
			});
	});

	const nameOf = (id: number) => {
		const u = users?.find((x) => x.id === id);
		return u ? `${u.display_name} (${u.username})` : `User ${id}`;
	};
	const candidates = $derived(
		(users ?? []).filter(
			(u) =>
				u.id !== ownerId && u.id !== session.user?.id && !members.some((m) => m.user_id === u.id)
		)
	);

	function add() {
		const id = Number(adding);
		if (!id || members.some((m) => m.user_id === id)) return;
		members = [...members, { user_id: id, role: 'viewer' }];
		adding = '';
	}

	async function save() {
		busy = true;
		try {
			members = await api.setAlbumMembers(albumId, members);
			notice.show('Sharing updated.');
			onclose();
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}
</script>

<Dialog title="Share album" {onclose}>
	<p class="quiet small">Viewers see the photos; editors can also add, remove and reorder them.</p>
	{#if members.length === 0}<p class="quiet">Only you, for now.</p>{/if}
	<ul>
		{#each members as member, i (member.user_id)}
			<li>
				<span>{nameOf(member.user_id)}</span>
				<select aria-label={`Role for ${nameOf(member.user_id)}`} bind:value={members[i].role}>
					<option value="viewer">Viewer</option>
					<option value="editor">Editor</option>
				</select>
				<button
					type="button"
					onclick={() => (members = members.filter((m) => m.user_id !== member.user_id))}
					>Remove</button
				>
			</li>
		{/each}
	</ul>
	<div class="add">
		{#if users}
			<select bind:value={adding} aria-label="Person to add">
				<option value="">Add a person…</option>
				{#each candidates as u (u.id)}<option value={String(u.id)}>{u.display_name}</option>{/each}
			</select>
		{:else}
			<input bind:value={adding} inputmode="numeric" placeholder="User id" aria-label="User id" />
		{/if}
		<button type="button" disabled={!adding} onclick={add}>Add</button>
	</div>
	{#snippet actions()}
		<button class="primary" type="button" disabled={busy} onclick={save}>Save</button>
	{/snippet}
</Dialog>

<style>
	ul {
		list-style: none;
		padding: 0;
		margin: 0.5rem 0;
	}
	li {
		display: grid;
		grid-template-columns: 1fr auto auto;
		align-items: center;
		gap: 0.5rem;
	}
	li button {
		color: var(--ink-2);
	}
	.add {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}
</style>
