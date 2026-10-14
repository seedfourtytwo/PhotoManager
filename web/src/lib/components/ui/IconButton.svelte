<script lang="ts">
	import type { HTMLButtonAttributes } from 'svelte/elements';
	import type { IconName } from '$lib/icons';
	import Icon from '../Icon.svelte';

	type Props = HTMLButtonAttributes & {
		icon: IconName;
		/** What the button does: its accessible name, its tooltip and its word. */
		label: string;
		/** Show the word under the icon even when the look does not ask for words. */
		worded?: boolean;
		/** A round fill behind the icon, for a button that stands on the page. */
		filled?: boolean;
	};
	let { icon, label, worded = false, filled = false, class: cls = '', ...rest }: Props = $props();
</script>

<button
	type="button"
	class="icon-button {cls}"
	class:worded
	class:filled
	aria-label={label}
	title={label}
	{...rest}
>
	<Icon name={icon} />
	<span class="word" aria-hidden="true">{label}</span>
</button>
