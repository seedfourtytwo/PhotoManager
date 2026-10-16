<script lang="ts">
	import { onMount } from 'svelte';
	import type { Person, Portrait as PortraitOut } from '$lib/api';
	import { api, notice } from '$lib/app.svelte';
	import {
		fitCircle,
		nudge,
		pan,
		photoLayout,
		wheelZoom,
		zoomAbout,
		type Circle
	} from '$lib/portrait';
	import Dialog from './Dialog.svelte';
	import Portrait from './Portrait.svelte';

	/**
	 * Choose a person's portrait (spec collections-people-places §6): which of their photos, and
	 * where the circle sits on it, like a crop tool. The square black stage shows the photo
	 * without its edits under a round window; what the window shows is what the server will
	 * cut. Drag to move, pinch or scroll to zoom (+ and − on the keys), double-tap to go back
	 * to the face as found.
	 */
	type Props = { person: Person; onclose: () => void; onsaved: (person: Person) => void };
	let { person, onclose, onsaved }: Props = $props();

	const FACE = 64;
	const circleOf = ({ cx, cy, size }: Circle): Circle => ({ cx, cy, size });

	// svelte-ignore state_referenced_locally (the dialog starts from the portrait it opened on)
	const opened = person.portrait;
	let faces = $state<PortraitOut[]>([]);
	let picked = $state<PortraitOut | null>(opened);
	let circle = $state<Circle>(circleOf(opened ?? { cx: 0.5, cy: 0.5, size: 1 }));
	/** Width / height of the photo on the stage; 0 until it has loaded. */
	let aspect = $state(0);
	let busy = $state(false);
	let stage: HTMLElement | undefined = $state();

	const layout = $derived(aspect ? photoLayout(circle, aspect) : null);

	onMount(() => {
		api
			.personFaces(person.id)
			.then((found) => (faces = found))
			.catch((e: unknown) => notice.error(e));
	});

	/** Another photo starts on its own automatic circle; the one in use, where it was left. */
	function pick(face: PortraitOut) {
		if (face.face_id === picked?.face_id) return;
		const inUse = person.portrait?.face_id === face.face_id ? person.portrait : face;
		picked = face;
		circle = circleOf(inUse);
		aspect = 0;
	}

	function loaded(event: Event) {
		const img = event.currentTarget as HTMLImageElement;
		if (!img.naturalWidth || !img.naturalHeight) return;
		aspect = img.naturalWidth / img.naturalHeight;
		circle = fitCircle(circle, aspect);
	}

	// --- moving and zooming the photo under the window ------------------------------------
	type Point = { x: number; y: number };
	// eslint-disable-next-line svelte/prefer-svelte-reactivity -- where the fingers were, not state
	const pointers = new Map<number, Point>();

	function down(event: PointerEvent) {
		if (event.button !== 0 || !aspect || !stage) return;
		stage.setPointerCapture(event.pointerId);
		pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
	}

	function move(event: PointerEvent) {
		const last = pointers.get(event.pointerId);
		if (!last || !stage) return;
		const box = stage.getBoundingClientRect();
		const next = { x: event.clientX, y: event.clientY };
		pointers.set(event.pointerId, next);
		const dx = (next.x - last.x) / box.width;
		const dy = (next.y - last.y) / box.height;
		if (pointers.size === 1) {
			circle = pan(circle, dx, dy, aspect);
			return;
		}
		// two fingers: zoom about the point between them, then follow it (it moves half as
		// far as this finger did)
		const other = [...pointers].find(([id]) => id !== event.pointerId)![1];
		const apart = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);
		const x = ((last.x + other.x) / 2 - box.left) / box.width;
		const y = ((last.y + other.y) / 2 - box.top) / box.height;
		const zoomed = zoomAbout(circle, apart(next, other) / apart(last, other), x, y, aspect);
		circle = pan(zoomed, dx / 2, dy / 2, aspect);
	}

	function wheel(event: WheelEvent) {
		if (!aspect || !stage) return;
		event.preventDefault();
		const box = stage.getBoundingClientRect();
		const x = (event.clientX - box.left) / box.width;
		const y = (event.clientY - box.top) / box.height;
		circle = zoomAbout(circle, wheelZoom(event.deltaY), x, y, aspect);
	}

	function keys(event: KeyboardEvent) {
		const next = aspect ? nudge(circle, event.key, aspect) : null;
		if (!next) return;
		event.preventDefault();
		circle = next;
	}

	/** Back to the circle the face was found in. */
	function refit() {
		if (!picked || !aspect) return;
		circle = fitCircle(circleOf(picked), aspect);
	}

	async function send(change: () => Promise<Person>) {
		if (busy) return;
		busy = true;
		try {
			onsaved(await change());
		} catch (e) {
			notice.error(e);
		} finally {
			busy = false;
		}
	}

	const save = () =>
		picked && send(() => api.setPortrait(person.id, { face_id: picked!.face_id, ...circle }));
	const useAutomatic = () => send(() => api.clearPortrait(person.id));
</script>

<Dialog title="Change portrait" wide {onclose}>
	<p class="quiet small">
		Choose a photo, then drag it and zoom until the face sits well in the circle.
	</p>
	{#if faces.length > 1}
		<ul class="faces">
			{#each faces as face, i (face.face_id)}
				<li>
					<button
						type="button"
						aria-label={`Photo ${i + 1}`}
						aria-pressed={face.face_id === picked?.face_id}
						onclick={() => pick(face)}
					>
						<Portrait portrait={face} size={FACE} />
					</button>
				</li>
			{/each}
		</ul>
	{/if}

	<!-- The stage is a custom control: drag, pinch and wheel, plus the keys. -->
	<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
	<div
		class="stage"
		role="group"
		aria-label="Portrait: drag to move, pinch or scroll to zoom; arrow keys move, plus and minus zoom"
		tabindex="0"
		bind:this={stage}
		onpointerdown={down}
		onpointermove={move}
		onpointerup={(e) => pointers.delete(e.pointerId)}
		onpointercancel={(e) => pointers.delete(e.pointerId)}
		onlostpointercapture={(e) => pointers.delete(e.pointerId)}
		onwheel={wheel}
		onkeydown={keys}
		ondblclick={refit}
	>
		{#if picked}
			{#key picked.face_id}
				<img
					src={api.previewUrl(picked.asset_id, { edit: 'none' })}
					alt=""
					draggable="false"
					class:waiting={!layout}
					style:left={layout && `${layout.left}%`}
					style:top={layout && `${layout.top}%`}
					style:width={layout && `${layout.width}%`}
					style:height={layout && `${layout.height}%`}
					onload={loaded}
				/>
			{/key}
		{/if}
		<span class="window"></span>
	</div>

	{#snippet actions()}
		<button type="button" disabled={busy || !person.portrait?.chosen} onclick={useAutomatic}
			>Use automatic</button
		>
		<button class="primary" type="button" disabled={busy || !aspect} onclick={save}>Save</button>
	{/snippet}
</Dialog>

<style>
	p {
		margin: 0 0 var(--s-3);
	}
	/* The photos to choose from: a rail that runs to the sheet's edges, the next one peeking. */
	.faces {
		list-style: none;
		display: flex;
		gap: var(--s-3);
		margin: 0 calc(-1 * var(--s-5)) var(--s-4);
		/* room for the ring of the one in use, which the scroller would cut */
		padding: var(--s-2) var(--s-5);
		overflow-x: auto;
		scrollbar-width: none;
	}
	.faces li {
		flex: none;
	}
	.faces button {
		display: block;
		padding: 0;
		border-radius: 50%;
		min-height: 0;
	}
	/* Selection is the accent's one job. */
	.faces button[aria-pressed='true'] {
		box-shadow:
			0 0 0 3px var(--raised),
			0 0 0 6px var(--accent);
	}
	.stage {
		position: relative;
		width: min(100%, 45rem, 60dvh);
		aspect-ratio: 1;
		margin: 0 auto var(--s-2);
		overflow: hidden;
		border-radius: var(--r-1);
		background: var(--bg);
		cursor: grab;
		touch-action: none;
		-webkit-user-select: none;
		user-select: none;
	}
	.stage:active {
		cursor: grabbing;
	}
	.stage:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	img {
		position: absolute;
		max-width: none;
		pointer-events: none;
	}
	img.waiting {
		visibility: hidden;
	}
	/* The round window: what is outside it is dimmed, and will not be in the portrait. The
	   shade alone draws its edge. */
	.window {
		position: absolute;
		inset: 0;
		border-radius: 50%;
		box-shadow: 0 0 0 100vmax var(--scrim);
		pointer-events: none;
	}
</style>
