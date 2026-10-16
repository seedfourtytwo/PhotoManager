import {
	defaultLevel,
	deviceOf,
	loadLevel,
	rowHeightAt,
	saveLevel,
	stepLevel,
	type Device
} from '$lib/grid-zoom';
import { settings } from './settings.svelte';

/** This browser's storage, or none where it is blocked (private browsing, a sandbox). */
function storage(): Storage | null {
	try {
		return globalThis.localStorage ?? null;
	} catch {
		return null;
	}
}

function saved(device: Device): number | null {
	const store = storage();
	return store ? loadLevel(store, device) : null;
}

/**
 * How large the photos of the grids are, per device (lib/grid-zoom.ts): the level this device
 * was zoomed to, else the look's photo size. A zoom is remembered on this device only.
 */
class GridZoom {
	#levels = $state<Record<Device, number | null>>({
		phone: saved('phone'),
		laptop: saved('laptop')
	});

	level(device: Device): number {
		return this.#levels[device] ?? defaultLevel(settings.thumbSize);
	}

	/** The row height for a screen this wide. */
	rowHeight(width: number): number {
		const device = deviceOf(width);
		return rowHeightAt(device, this.level(device));
	}

	/** One level bigger (+1) or smaller (−1); false when it is at that end already. */
	step(width: number, by: 1 | -1): boolean {
		const device = deviceOf(width);
		const from = this.level(device);
		const to = stepLevel(from, by);
		if (to === from) return false;
		this.#levels[device] = to;
		const store = storage();
		if (store) saveLevel(store, device, to);
		return true;
	}
}

export const gridZoom = new GridZoom();
