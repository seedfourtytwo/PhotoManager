<script lang="ts">
	import { isPin, PIN_LENGTH, type Role, type User } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { PIN_FIELD } from '$lib/pin';
	import Dialog from '../Dialog.svelte';

	let users = $state<User[]>([]);
	let creating = $state(false);
	let resetting = $state<User | null>(null);
	let form = $state({ username: '', display_name: '', pin: '', role: 'member' as Role });
	let newPin = $state('');

	async function load() {
		try {
			users = await api.users();
		} catch (e) {
			notice.error(e);
		}
	}
	$effect(() => void load());

	let pending = $state<number | null>(null);

	/** One change per person at a time; a refused one shows the server's reason and is undone. */
	async function patch(
		user: User,
		body: Parameters<typeof api.updateUser>[1],
		control?: HTMLSelectElement
	) {
		if (pending !== null) return false;
		pending = user.id;
		try {
			const updated = await api.updateUser(user.id, body);
			users = users.map((u) => (u.id === updated.id ? updated : u));
			return true;
		} catch (e) {
			notice.error(e);
			// The select already shows the refused value: put the real one back.
			if (control) control.value = user.role;
			await load();
			return false;
		} finally {
			pending = null;
		}
	}

	async function create() {
		try {
			await api.createUser({ ...form, username: form.username.trim() });
			notice.show(`Created ${form.username}. Give them their PIN in person.`);
			creating = false;
			form = { username: '', display_name: '', pin: '', role: 'member' };
			await load();
		} catch (e) {
			notice.error(e);
		}
	}

	async function reset() {
		if (!resetting) return;
		await patch(resetting, { pin: newPin });
		notice.show(`New PIN set for ${resetting.username}.`);
		resetting = null;
		newPin = '';
	}
</script>

<section aria-labelledby="a-users">
	<header>
		<h2 id="a-users">People</h2>
		<button type="button" onclick={() => (creating = true)}>Add person</button>
	</header>
	<table>
		<thead>
			<tr><th>Name</th><th>User name</th><th>Role</th><th>Status</th><th></th></tr>
		</thead>
		<tbody>
			{#each users as user (user.id)}
				<tr class:off={user.disabled}>
					<td>{user.display_name}</td>
					<td class="quiet">{user.username}</td>
					<td>
						<select
							aria-label={`Role of ${user.username}`}
							value={user.role}
							disabled={pending === user.id}
							onchange={(e) =>
								patch(user, { role: e.currentTarget.value as Role }, e.currentTarget)}
						>
							<option value="admin">Admin</option>
							<option value="member">Member</option>
							<option value="guest">Guest (view and download)</option>
						</select>
					</td>
					<td>
						<span class="state" class:quiet={!user.disabled}
							>{user.disabled ? 'Disabled' : 'Active'}</span
						>
						{#if user.id !== session.user?.id}
							<button
								type="button"
								disabled={pending === user.id}
								onclick={() => patch(user, { disabled: !user.disabled })}
							>
								{user.disabled ? 'Enable' : 'Disable'}
							</button>
						{:else}<span class="quiet">· you</span>{/if}
					</td>
					<td><button type="button" onclick={() => (resetting = user)}>Reset PIN</button></td>
				</tr>
			{/each}
		</tbody>
	</table>
</section>

{#if creating}
	<Dialog title="Add person" onclose={() => (creating = false)}>
		<label class="field">User name <input bind:value={form.username} autocomplete="off" /></label>
		<label class="field">Name <input bind:value={form.display_name} /></label>
		<label class="field"
			>PIN <input
				{...PIN_FIELD}
				bind:value={form.pin}
				autocomplete="off"
				aria-describedby="new-pin-hint"
			/></label
		>
		<p class="quiet small hint" id="new-pin-hint">
			Exactly {PIN_LENGTH} digits. Give it to them in person; they can change it in Settings.
		</p>
		<label class="field">
			Role
			<select bind:value={form.role}>
				<option value="member">Member</option>
				<option value="guest">Guest (view and download)</option>
				<option value="admin">Admin</option>
			</select>
		</label>
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={!form.username.trim() || !isPin(form.pin)}
				onclick={create}>Add</button
			>
		{/snippet}
	</Dialog>
{:else if resetting}
	<Dialog title={`New PIN for ${resetting.username}`} onclose={() => (resetting = null)}>
		<label class="field">PIN <input {...PIN_FIELD} bind:value={newPin} autocomplete="off" /></label>
		<p class="quiet small">Exactly {PIN_LENGTH} digits.</p>
		{#snippet actions()}
			<button class="primary" type="button" disabled={!isPin(newPin)} onclick={reset}
				>Set PIN</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	header button,
	td button {
		color: var(--ink-2);
	}
	table {
		border-collapse: collapse;
		width: 100%;
	}
	th {
		text-align: left;
		font-weight: 600;
		font-size: var(--fs-12);
		color: var(--ink-2);
		border-bottom: 1px solid var(--hairline);
		padding: var(--s-1) var(--s-3) var(--s-1) 0;
	}
	td {
		padding: var(--s-1) var(--s-3) var(--s-1) 0;
		border-bottom: 1px solid var(--hairline);
	}
	tr:last-child td {
		border-bottom: 0;
	}
	td select {
		border-bottom: 0;
	}
	.state {
		margin-right: var(--s-1);
	}
	.hint {
		margin: calc(-1 * var(--s-3)) 0 var(--s-4);
	}
	tr.off td:first-child {
		color: var(--ink-2);
		text-decoration: line-through;
	}
	@media (max-width: 639px) {
		table,
		tbody,
		tr,
		td {
			display: block;
		}
		thead {
			display: none;
		}
		tr {
			padding: var(--s-2) 0;
			border-bottom: 1px solid var(--hairline);
		}
		td {
			border: 0;
			padding: 0;
		}
		td:first-child {
			font-weight: 600;
		}
		td button {
			margin-left: calc(-1 * var(--s-2));
		}
	}
</style>
