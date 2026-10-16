<script lang="ts">
	import type { AlbumMember, DirectoryEntry } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { initialOf } from '$lib/nav';
	import Dialog from './Dialog.svelte';
	import IconButton from './ui/IconButton.svelte';
	import Segmented from './ui/Segmented.svelte';

	/**
	 * Who sees an album (spec collections-people-places §3): each member with their initial and
	 * a Viewer | Editor choice, × to take them off; under them everyone else, one tap each to
	 * add as a viewer. Save sends the whole list.
	 */
	type Props = { albumId: number; ownerId: number; onclose: () => void };
	let { albumId, ownerId, onclose }: Props = $props();

	// null until the current members are in: Save replaces the whole list, so saving a list
	// that never loaded would remove everyone who was already there.
	let members = $state<AlbumMember[] | null>(null);
	let failed = $state(false);
	let users = $state<DirectoryEntry[]>([]);
	let busy = $state(false);

	$effect(() => {
		api
			.albumMembers(albumId)
			.then((m) => (members = m))
			.catch((e: unknown) => {
				failed = true;
				notice.error(e);
			});
		// v1.1: any member may read the directory (ids and names), so owners share by name.
		api
			.userDirectory()
			.then((u) => (users = u))
			.catch((e: unknown) => notice.error(e));
	});

	const ROLES: { value: AlbumMember['role']; label: string }[] = [
		{ value: 'viewer', label: 'Viewer' },
		{ value: 'editor', label: 'Editor' }
	];
	const nameOf = (id: number) => users.find((u) => u.id === id)?.display_name ?? `User ${id}`;
	const addable = $derived(
		users.filter(
			(u) =>
				u.id !== ownerId && u.id !== session.user?.id && !members?.some((m) => m.user_id === u.id)
		)
	);

	function setRole(id: number, role: AlbumMember['role']) {
		members = members?.map((m) => (m.user_id === id ? { ...m, role } : m)) ?? null;
	}

	async function save() {
		if (!members) return;
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

{#snippet initial(name: string)}
	<span class="initial" aria-hidden="true">{initialOf(name)}</span>
{/snippet}

<Dialog title="Share album" {onclose}>
	<p class="quiet small">Viewers see the photos; editors can also add, remove and reorder them.</p>
	{#if members}
		{#if members.length === 0}<p class="quiet">Only you, for now.</p>{/if}
		{#if members.length}
			<ul class="people" aria-label="Shared with">
				{#each members as member (member.user_id)}
					{@const name = nameOf(member.user_id)}
					<li>
						{@render initial(name)}
						<span class="name">{name}</span>
						<Segmented
							label={`Role for ${name}`}
							options={ROLES}
							value={member.role}
							onchange={(role) => setRole(member.user_id, role)}
						/>
						<IconButton
							icon="x"
							label={`Remove ${name}`}
							onclick={() =>
								(members = members?.filter((m) => m.user_id !== member.user_id) ?? null)}
						/>
					</li>
				{/each}
			</ul>
		{/if}
		{#if addable.length}
			<h3 class="small quiet">Add people</h3>
			<ul class="people" aria-label="Add people">
				{#each addable as user (user.id)}
					<li>
						<button
							type="button"
							class="add"
							aria-label={`Add ${user.display_name}`}
							onclick={() => (members = [...(members ?? []), { user_id: user.id, role: 'viewer' }])}
						>
							{@render initial(user.display_name)}
							<span class="name">{user.display_name}</span>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	{:else if failed}
		<p role="alert">
			Could not load who this album is shared with. Close this and open Share again.
		</p>
	{:else}
		<p class="quiet" role="status">Loading…</p>
	{/if}
	{#snippet actions()}
		<button class="primary" type="button" disabled={busy || !members} onclick={save}>Save</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-2);
	}
	h3 {
		margin: var(--s-4) 0 var(--s-1);
		font-weight: 600;
	}
	.people {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: var(--s-1);
	}
	.people li {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		min-height: var(--target);
	}
	.name {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-weight: 600;
	}
	/* Someone's initial on a disc: the people of the house have no photo on this sheet. */
	.initial {
		display: grid;
		place-items: center;
		flex: none;
		width: 2.25rem;
		height: 2.25rem;
		border-radius: 50%;
		background: var(--fill);
		color: var(--ink);
		font-weight: 650;
	}
	.add {
		display: flex;
		align-items: center;
		gap: var(--s-3);
		width: 100%;
		min-height: var(--target);
		padding: 0;
		text-align: left;
		color: var(--ink);
	}
	.add .name {
		font-weight: 500;
	}
</style>
