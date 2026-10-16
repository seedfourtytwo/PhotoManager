/** Map math: plate carrée projection and grid clustering (no tiles, no map library). */
import type { Id, MapPoint, Place } from './api/types';

export type Viewport = { width: number; height: number };

/** Equirectangular: longitude and latitude map linearly onto a 2:1 frame. */
export function project(lat: number, lon: number, view: Viewport): [number, number] {
	return [((lon + 180) / 360) * view.width, ((90 - lat) / 180) * view.height];
}

/** A window onto the 360 × 180 map: its top-left corner and its width (its height follows
 *  from the frame's shape). */
export type MapView = { x: number; y: number; w: number };

/** The closest the map zooms in (degrees across): past it the 1:110m outline is only blocks. */
export const MIN_VIEW = 2;
const WORLD = { x: 0, y: 0, w: 360 };

/**
 * The view kept on the map: no wider than the world, no closer than `MIN_VIEW`, and not past
 * its edges. A frame taller than the world (a phone held upright) shows it whole, centred.
 * `aspect` is the frame's width ÷ height.
 */
export function clampView(view: MapView, aspect: number): MapView {
	const w = Math.min(360, Math.max(MIN_VIEW, view.w));
	const h = w / aspect;
	const y = h >= 180 ? (180 - h) / 2 : Math.min(Math.max(view.y, 0), 180 - h);
	return { w, x: Math.min(Math.max(view.x, 0), 360 - w), y };
}

/**
 * The view that frames every point with `pad` of their spread on each side (spec §7: the map
 * opens on the photos, not on the world), in a frame of `aspect`. The whole world when there
 * are none.
 */
export function fitView(points: readonly MapPoint[], aspect: number, pad = 0.1): MapView {
	if (!points.length) return { ...WORLD };
	let [left, top] = project(points[0].lat, points[0].lon, MAP);
	let [right, bottom] = [left, top];
	for (const p of points) {
		const [x, y] = project(p.lat, p.lon, MAP);
		left = Math.min(left, x);
		right = Math.max(right, x);
		top = Math.min(top, y);
		bottom = Math.max(bottom, y);
	}
	const across = (right - left) * (1 + 2 * pad);
	const down = (bottom - top) * (1 + 2 * pad);
	const w = Math.max(across, down * aspect, MIN_VIEW);
	const cx = (left + right) / 2;
	const cy = (top + bottom) / 2;
	return clampView({ w, x: cx - w / 2, y: cy - w / aspect / 2 }, aspect);
}

/** The whole map, as `project` draws it. */
const MAP: Viewport = { width: 360, height: 180 };

/** A gesture, as the picture moved on screen: by (tx, ty) px, scaled by s about its corner. */
export type Gesture = { tx: number; ty: number; s: number };

/** The view once a gesture is let go: what the moved picture shows now (not yet clamped). */
export function moved(view: MapView, { tx, ty, s }: Gesture, pxPerUnit: number): MapView {
	return { x: view.x - tx / s / pxPerUnit, y: view.y - ty / s / pxPerUnit, w: view.w / s };
}

export type Cluster = {
	x: number;
	y: number;
	ids: Id[];
	bounds: { south: number; west: number; north: number; east: number };
};

function merge(a: Cluster, b: Cluster): Cluster {
	const na = a.ids.length;
	const nb = b.ids.length;
	return {
		x: (a.x * na + b.x * nb) / (na + nb),
		y: (a.y * na + b.y * nb) / (na + nb),
		ids: [...a.ids, ...b.ids],
		bounds: {
			south: Math.min(a.bounds.south, b.bounds.south),
			north: Math.max(a.bounds.north, b.bounds.north),
			west: Math.min(a.bounds.west, b.bounds.west),
			east: Math.max(a.bounds.east, b.bounds.east)
		}
	};
}

/** Merge clusters until no two dots (of `radius(count)`) overlap: overlapping dots hide each
 * other and steal each other's clicks. Few clusters on screen, so pairwise is fine. */
function separate(clusters: Cluster[], radius: (count: number) => number): Cluster[] {
	const out = [...clusters];
	for (let merged = true; merged;) {
		merged = false;
		search: for (let i = 0; i < out.length; i++)
			for (let j = i + 1; j < out.length; j++) {
				const [a, b] = [out[i], out[j]];
				if (Math.hypot(a.x - b.x, a.y - b.y) < radius(a.ids.length) + radius(b.ids.length)) {
					out.splice(j, 1);
					out[i] = merge(a, b);
					merged = true;
					break search;
				}
			}
	}
	return out;
}

/**
 * Bucket points into square cells of `cell` pixels; each cluster sits at its points' centroid.
 * With `radius`, clusters whose dots would overlap are merged too.
 * Largest first, so small clusters draw on top and stay clickable.
 */
export function clusterPoints(
	points: readonly MapPoint[],
	view: Viewport,
	cell: number,
	radius?: (count: number) => number
): Cluster[] {
	const buckets = new Map<string, { sx: number; sy: number; cluster: Cluster }>();
	for (const p of points) {
		const [x, y] = project(p.lat, p.lon, view);
		const key = `${Math.floor(x / cell)}:${Math.floor(y / cell)}`;
		let bucket = buckets.get(key);
		if (!bucket) {
			const bounds = { south: p.lat, north: p.lat, west: p.lon, east: p.lon };
			bucket = { sx: 0, sy: 0, cluster: { x: 0, y: 0, ids: [], bounds } };
			buckets.set(key, bucket);
		}
		bucket.sx += x;
		bucket.sy += y;
		// Bounds are tracked here, not with Math.min(...all): a big bucket overflows the stack.
		const { ids, bounds } = bucket.cluster;
		ids.push(p.id);
		if (p.lat < bounds.south) bounds.south = p.lat;
		if (p.lat > bounds.north) bounds.north = p.lat;
		if (p.lon < bounds.west) bounds.west = p.lon;
		if (p.lon > bounds.east) bounds.east = p.lon;
	}
	const clusters = [...buckets.values()].map(({ sx, sy, cluster }) => ({
		...cluster,
		x: sx / cluster.ids.length,
		y: sy / cluster.ids.length
	}));
	return (radius ? separate(clusters, radius) : clusters).sort(
		(a, b) => b.ids.length - a.ids.length
	);
}

/** The clusters inside a window onto the map (`margin` keeps dots that straddle its edge). */
export function clustersInView(
	clusters: readonly Cluster[],
	view: { x: number; y: number; w: number; h: number },
	margin = 0
): Cluster[] {
	return clusters.filter(
		(c) =>
			c.x >= view.x - margin &&
			c.x <= view.x + view.w + margin &&
			c.y >= view.y - margin &&
			c.y <= view.y + view.h + margin
	);
}

/** Dot radius grows with the square root of the count, so area is proportional to photos. */
/**
 * The cluster closest to a point of the map. The map clusters again at every zoom, so a dot
 * that was chosen is found again by where it was, not kept as the dot it used to be.
 */
export function nearestCluster(
	clusters: readonly Cluster[],
	at: { x: number; y: number }
): Cluster | null {
	let best: Cluster | null = null;
	let bestDistance = Infinity;
	for (const cluster of clusters) {
		const distance = Math.hypot(cluster.x - at.x, cluster.y - at.y);
		if (distance < bestDistance) [best, bestDistance] = [cluster, distance];
	}
	return best;
}

export function clusterRadius(count: number, unit = 2.5): number {
	return unit * Math.sqrt(count);
}

/** Most specific place name shared by most photos: city, else region, else country. */
export function dominantPlace(places: readonly (Place | null)[]): string | null {
	for (const key of ['city', 'region', 'country'] as const) {
		const counts = new Map<string, number>();
		for (const p of places) {
			const name = p?.[key];
			if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
		}
		const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
		if (best && best[1] * 2 >= places.length) return best[0];
	}
	return null;
}

export function placeLabel(place: Place | null): string | null {
	if (!place) return null;
	return [place.city, place.region, place.country].filter(Boolean).join(', ') || null;
}
