<script lang="ts">
	import { isPin, PIN_LENGTH, type ManagedUser, type Role } from '$lib/api';
	import { api, notice, session } from '$lib/app.svelte';
	import { PIN_FIELD } from '$lib/pin';
	import Dialog from '../Dialog.svelte';
	import IconButton from '../ui/IconButton.svelte';
	import TileGroup from '../ui/TileGroup.svelte';
	import TileRow from '../ui/TileRow.svelte';
	import ActionCard from './ActionCard.svelte';
	import ActionCards from './ActionCards.svelte';
	import LookForm from './LookForm.svelte';

	const ROLE: Record<Role, string> = { admin: 'Admin', member: 'Member', guest: 'Guest' };

	let users = $state<ManagedUser[]>([]);
	let creating = $state(false);
	let resetting = $state<ManagedUser | null>(null);
	let styling = $state<ManagedUser | null>(null);
	let form = $state({ username: '', display_name: '', pin: '', role: 'member' as Role });
	let newPin = $state('');
	/** Whose sheet is open: their role, their actions, their user name. */
	let openId = $state<number | null>(null);
	const open = $derived(users.find((u) => u.id === openId) ?? null);

	/** "Member", "Admin, you", "Guest, Disabled, Locked". */
	function lineOf(user: ManagedUser): string {
		const role = user.id === session.user?.id ? `${ROLE[user.role]}, you` : ROLE[user.role];
		return [role, user.disabled && 'Disabled', user.locked && 'Locked'].filter(Boolean).join(', ');
	}

	/** An action that opens its own dialog takes the sheet's place. */
	function then(next: (user: ManagedUser) => void) {
		const user = open;
		openId = null;
		if (user) next(user);
	}

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
		user: ManagedUser,
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

	function closeReset() {
		resetting = null;
		newPin = '';
	}

	async function reset() {
		// The dialog may be cancelled while the request is on its way: remember who it was for.
		const who = resetting;
		if (!who || !(await patch(who, { pin: newPin }))) return;
		notice.show(`New PIN set for ${who.username}.`);
		if (resetting?.id === who.id) closeReset();
	}

	/** Thirty wrong PINs lock an account until someone lifts it here (or sets a new PIN). */
	async function unlock(user: ManagedUser) {
		if (pending !== null) return;
		pending = user.id;
		try {
			await api.unlockUser(user.id);
			notice.show(`${user.username} can try their PIN again.`);
			await load();
		} catch (e) {
			notice.error(e);
		} finally {
			pending = null;
		}
	}
</script>

<TileGroup label="People">
	{#snippet action()}
		<IconButton icon="plus" label="Add person" onclick={() => (creating = true)} />
	{/snippet}
	{#each users as user (user.id)}
		<TileRow
			icon="person"
			title={user.display_name}
			line={lineOf(user)}
			onclick={() => (openId = user.id)}
		/>
	{/each}
</TileGroup>

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
	<Dialog title={`New PIN for ${resetting.username}`} onclose={closeReset}>
		<label class="field">PIN <input {...PIN_FIELD} bind:value={newPin} autocomplete="off" /></label>
		<p class="quiet small">Exactly {PIN_LENGTH} digits.</p>
		{#snippet actions()}
			<button
				class="primary"
				type="button"
				disabled={!isPin(newPin) || pending !== null}
				onclick={reset}>Set PIN</button
			>
		{/snippet}
	</Dialog>
{:else if styling}
	{#key styling.id}
		<LookForm user={styling} onclose={() => (styling = null)} />
	{/key}
{:else if open}
	{@const self = open.id === session.user?.id}
	<Dialog title={open.display_name} cancelLabel="Close" onclose={() => (openId = null)}>
		<p class="quiet small">User name <span class="data">{open.username}</span></p>
		<label class="field">
			Role
			<select
				value={open.role}
				disabled={pending !== null}
				onchange={(e) => patch(open, { role: e.currentTarget.value as Role }, e.currentTarget)}
			>
				<option value="admin">Admin</option>
				<option value="member">Member</option>
				<option value="guest">Guest (view and download)</option>
			</select>
		</label>
		<ActionCards>
			<ActionCard
				icon="sliders"
				label="Look"
				disabled={pending !== null}
				onclick={() => then((user) => (styling = user))}
			/>
			<ActionCard
				icon="lock"
				label="Reset PIN"
				disabled={pending !== null}
				onclick={() => then((user) => (resetting = user))}
			/>
			{#if open.locked}
				<ActionCard
					icon="refresh"
					label="Unlock"
					disabled={pending !== null}
					onclick={() => open && unlock(open)}
				/>
			{/if}
			{#if !self}
				<ActionCard
					icon="power"
					label={open.disabled ? 'Enable' : 'Disable'}
					disabled={pending !== null}
					onclick={() => open && patch(open, { disabled: !open.disabled })}
				/>
			{/if}
		</ActionCards>
	</Dialog>
{/if}

<style>
	.hint {
		margin: calc(-1 * var(--s-3)) 0 var(--s-4);
	}
</style>
