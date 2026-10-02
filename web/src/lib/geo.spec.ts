import { describe, expect, it } from 'vitest';
import { clusterPoints, clusterRadius, dominantPlace, placeLabel, project } from './geo';

const view = { width: 360, height: 180 };

describe('project', () => {
	it('maps the world onto a 2:1 frame', () => {
		expect(project(0, 0, view)).toEqual([180, 90]);
		expect(project(90, -180, view)).toEqual([0, 0]);
		expect(project(-90, 180, view)).toEqual([360, 180]);
	});
});

describe('clusterPoints', () => {
	const points = [
		{ id: 1, lat: 48.85, lon: 2.35 }, // Paris
		{ id: 2, lat: 48.86, lon: 2.34 },
		{ id: 3, lat: 44.89, lon: 1.22 }, // Dordogne
		{ id: 4, lat: 37.54, lon: -122.51 } // Montara
	];

	it('groups nearby points and keeps far ones apart', () => {
		const clusters = clusterPoints(points, view, 2);
		expect(clusters.map((c) => c.ids)).toEqual([[1, 2], [3], [4]]);
	});

	it('merges more at coarser cells, largest first', () => {
		const clusters = clusterPoints(points, view, 20);
		expect(clusters[0].ids).toEqual([1, 2, 3]);
	});

	it('reports the bounds of each cluster', () => {
		const [paris] = clusterPoints(points, view, 2);
		expect(paris.bounds).toEqual({ south: 48.85, north: 48.86, west: 2.34, east: 2.35 });
	});

	it('merges clusters whose dots would overlap, so every dot stays clickable', () => {
		// Two dense places one cell apart: as dots of radius 2*sqrt(n) they would overlap.
		const near = [
			...Array.from({ length: 40 }, (_, i) => ({ id: i, lat: 45, lon: 1 })),
			...Array.from({ length: 30 }, (_, i) => ({ id: 100 + i, lat: 45, lon: 4.5 })),
			{ id: 999, lat: -30, lon: 120 }
		];
		const radius = (n: number) => 2 * Math.sqrt(n);
		const apart = clusterPoints(near, view, 3);
		expect(apart).toHaveLength(3);
		const merged = clusterPoints(near, view, 3, radius);
		expect(merged.map((c) => c.ids.length)).toEqual([70, 1]);
		for (const [i, a] of merged.entries())
			for (const b of merged.slice(i + 1))
				expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThanOrEqual(
					radius(a.ids.length) + radius(b.ids.length)
				);
		expect(merged[0].bounds).toEqual({ south: 45, north: 45, west: 1, east: 4.5 });
		expect(merged[0].x).toBeCloseTo((40 * 181 + 30 * 184.5) / 70);
	});

	it('returns nothing for no points', () => {
		expect(clusterPoints([], view, 10)).toEqual([]);
	});
});

describe('clusterRadius', () => {
	it('scales area, not radius, with the count', () => {
		expect(clusterRadius(4) / clusterRadius(1)).toBeCloseTo(2);
	});
});

describe('dominantPlace', () => {
	const paris = { country: 'France', region: 'Île-de-France', city: 'Paris' };
	const sarlat = { country: 'France', region: 'Nouvelle-Aquitaine', city: 'Sarlat' };

	it('prefers the city most photos share', () => {
		expect(dominantPlace([paris, paris, sarlat])).toBe('Paris');
	});

	it('falls back to a shared country', () => {
		expect(dominantPlace([paris, sarlat, sarlat, paris, null])).toBe('France');
		expect(dominantPlace([null])).toBeNull();
	});

	it('labels places compactly', () => {
		expect(placeLabel(paris)).toBe('Paris, Île-de-France, France');
		expect(placeLabel(null)).toBeNull();
	});
});
