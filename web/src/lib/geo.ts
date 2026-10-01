/** Map math: plate carrée projection and grid clustering (no tiles, no map library). */
import type { Id, MapPoint, Place } from './api/types';

export type Viewport = { width: number; height: number };

/** Equirectangular: longitude and latitude map linearly onto a 2:1 frame. */
export function project(lat: number, lon: number, view: Viewport): [number, number] {
	return [((lon + 180) / 360) * view.width, ((90 - lat) / 180) * view.height];
}

export type Cluster = {
	x: number;
	y: number;
	ids: Id[];
	bounds: { south: number; west: number; north: number; east: number };
};

/**
 * Bucket points into square cells of `cell` pixels; each cluster sits at its points' centroid.
 * Largest first, so small clusters draw on top and stay clickable.
 */
export function clusterPoints(
	points: readonly MapPoint[],
	view: Viewport,
	cell: number
): Cluster[] {
	const buckets = new Map<string, { sx: number; sy: number; points: MapPoint[] }>();
	for (const p of points) {
		const [x, y] = project(p.lat, p.lon, view);
		const key = `${Math.floor(x / cell)}:${Math.floor(y / cell)}`;
		const bucket = buckets.get(key) ?? { sx: 0, sy: 0, points: [] };
		bucket.sx += x;
		bucket.sy += y;
		bucket.points.push(p);
		buckets.set(key, bucket);
	}
	return [...buckets.values()]
		.map(({ sx, sy, points: ps }) => ({
			x: sx / ps.length,
			y: sy / ps.length,
			ids: ps.map((p) => p.id),
			bounds: {
				south: Math.min(...ps.map((p) => p.lat)),
				north: Math.max(...ps.map((p) => p.lat)),
				west: Math.min(...ps.map((p) => p.lon)),
				east: Math.max(...ps.map((p) => p.lon))
			}
		}))
		.sort((a, b) => b.ids.length - a.ids.length);
}

/** Dot radius grows with the square root of the count, so area is proportional to photos. */
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
