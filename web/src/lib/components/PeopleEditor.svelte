<script lang="ts" generics="Role extends string">
	type Person = { user_id: number; role: Role };
	type Named = { id: number; display_name: string };

	/** People, each with a role and Remove, and a select to add one more. The caller loads
	 *  and saves the list; here it is only edited. */
	type Props = {
		people: Person[];
		/** Each role with its words; a person is added with the first one. */
		roles: [Role, string][];
		/** What a role is called here: "Access for Lea", "Role for Lea". */
		roleWord: string;
		/** Everyone a name may be needed for. */
		users: Named[];
		/** Who may be added; those already listed are left out here. */
		addable: Named[];
		/** Laid out as a list with the add row under it, instead of as rows of the dialog. */
		list?: boolean;
	};
	let { people = $bindable(), roles, roleWord, users, addable, list = false }: Props = $props();

	let adding = $state('');

	const nameOf = (id: number) => users.find((u) => u.id === id)?.display_name ?? `User ${id}`;
	const candidates = $derived(addable.filter((u) => !people.some((p) => p.user_id === u.id)));

	function add() {
		const id = Number(adding);
		if (!id || people.some((p) => p.user_id === id)) return;
		people = [...people, { user_id: id, role: roles[0][0] }];
		adding = '';
	}
</script>

{#snippet person(entry: Person, i: number)}
	<span>{nameOf(entry.user_id)}</span>
	<select aria-label={`${roleWord} for ${nameOf(entry.user_id)}`} bind:value={people[i].role}>
		{#each roles as [value, text] (value)}<option {value}>{text}</option>{/each}
	</select>
	<button type="button" onclick={() => (people = people.filter((p) => p.user_id !== entry.user_id))}
		>Remove</button
	>
{/snippet}

{#snippet adder()}
	<select bind:value={adding} aria-label="Person to add">
		<option value="">Add a person…</option>
		{#each candidates as u (u.id)}<option value={String(u.id)}>{u.display_name}</option>{/each}
	</select>
	<button type="button" disabled={!adding} onclick={add}>Add</button>
{/snippet}

{#if list}
	{#if people.length}
		<ul class="tiles">
			{#each people as entry, i (entry.user_id)}
				<li class="tile-row">{@render person(entry, i)}</li>
			{/each}
		</ul>
	{/if}
	<div class="add">{@render adder()}</div>
{:else}
	{#each people as entry, i (entry.user_id)}
		<div class="row">{@render person(entry, i)}</div>
	{/each}
	<div class="row">{@render adder()}</div>
{/if}

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
	@media (max-width: 639px) {
		.row {
			grid-template-columns: 1fr auto;
		}
		.row > :first-child {
			grid-column: 1 / -1;
		}
	}
	/* One tile per person, on the sheet's fill; space, not lines, between them. */
	ul {
		margin: var(--s-3) 0;
	}
	li {
		display: grid;
		grid-template-columns: 1fr auto auto;
		gap: var(--s-2);
		padding-block: var(--s-1);
	}
	li > span {
		overflow-wrap: anywhere;
	}
	li button {
		color: var(--ink-2);
	}
	.add {
		display: flex;
		gap: var(--s-2);
		align-items: center;
	}
	.add select {
		flex: 1;
	}
</style>
