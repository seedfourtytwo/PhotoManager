<script lang="ts">
	import type { PlainProblem } from '$lib/backups';

	/**
	 * Something that went wrong, in plain words: what happened, one line of what to do, and the
	 * machine's own text folded away under Details (spec flight/admin-settings-auth §0).
	 */
	let { problem }: { problem: PlainProblem } = $props();
</script>

<div class="plain-problem">
	<p class="headline">{problem.headline}</p>
	<p class="line">{problem.line}</p>
	{#if problem.details}
		<details>
			<summary>Details</summary>
			<p class="raw">{problem.details}</p>
		</details>
	{/if}
</div>

<style>
	.plain-problem {
		display: grid;
		gap: var(--s-1);
	}
	p {
		margin: 0;
	}
	.headline {
		font-weight: 650;
	}
	.line {
		color: var(--ink-2);
	}
	details {
		font-size: var(--fs-13);
		color: var(--ink-2);
	}
	summary {
		cursor: pointer;
		width: max-content;
		min-height: var(--target);
		display: flex;
		align-items: center;
		font-weight: 600;
	}
	.raw {
		overflow-wrap: anywhere;
		font-family: var(--font-code);
	}
</style>
