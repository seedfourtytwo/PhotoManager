<script lang="ts">
	import { MIN_PASSWORD, type Role, type User } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import Dialog from '../Dialog.svelte';

	let users = $state<User[]>([]);
	let creating = $state(false);
	let resetting = $state<User | null>(null);
	let form = $state({ username: '', display_name: '', password: '', role: 'member' as Role });
	let newPassword = $state('');

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
			notice.show(`Created ${form.username}. Give them their password in person.`);
			creating = false;
			form = { username: '', display_name: '', password: '', role: 'member' };
			await load();
		} catch (e) {
			notice.error(e);
		}
	}

	async function reset() {
		if (!resetting) return;
		await patch(resetting, { password: newPassword });
		notice.show(`New password set for ${resetting.username}.`);
		resetting = null;
		newPassword = '';
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
					<td><button type="button" onclick={() => (resetting = user)}>Reset password</button></td>
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
			>Password <input
				type="password"
				bind:value={form.password}
				autocomplete="new-password"
				aria-describedby="new-pw-hint"
			/></label
		>
		<p class="quiet small hint" id="new-pw-hint" aria-live="polite">
			{#if form.password.length && form.password.length < MIN_PASSWORD}
				{MIN_PASSWORD - form.password.length} more character{MIN_PASSWORD - form.password.length ===
				1
					? ''
					: 's'} needed.
			{:else}
				At least {MIN_PASSWORD} characters.
			{/if}
			Give it to them in person; they can change it in Settings.
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
				disabled={!form.username.trim() || form.password.length < MIN_PASSWORD}
				onclick={create}>Add</button
			>
		{/snippet}
	</Dialog>
{:else if resetting}
	<Dialog title={`New password for ${resetting.username}`} onclose={() => (resetting = null)}>
		<label class="field"
			>Password <input
				type="password"
				bind:value={newPassword}
				autocomplete="new-password"
			/></label
		>
		<p class="quiet small">At least {MIN_PASSWORD} characters.</p>
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={newPassword.length < MIN_PASSWORD}
				onclick={reset}>Set password</button
			>
		{/snippet}
	</Dialog>
{/if}

<style>
	header {
		display: flex;
		gap: 1rem;
		align-items: baseline;
	}
	header button,
	td button {
		color: var(--ink-2);
	}
	h2 {
		font-size: var(--fs-16);
		margin: 1rem 0 0.5rem;
	}
	table {
		border-collapse: collapse;
		width: 100%;
	}
	th {
		text-align: left;
		font-weight: 400;
		font-size: var(--fs-12);
		color: var(--ink-2);
		border-bottom: 1px solid var(--hairline);
		padding: 0.25rem 0.5rem 0.25rem 0;
	}
	td {
		padding: 0.25rem 0.5rem 0.25rem 0;
	}
	.state {
		margin-right: 0.25rem;
	}
	.hint {
		margin: -0.5rem 0 0.75rem;
	}
	tr.off td:first-child {
		color: var(--ink-2);
		text-decoration: line-through;
	}
	.field {
		display: grid;
		gap: 0.15rem;
		margin-bottom: 0.75rem;
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
			padding: 0.5rem 0;
			border-bottom: 1px solid var(--hairline);
		}
	}
</style>
