import { describe, expect, it } from 'vitest';
import {
	MIN_VIEW,
	clampView,
	clusterPoints,
	clusterRadius,
	clustersInView,
	dominantPlace,
	fitView,
	moved,
	nearestCluster,
	placeLabel,
	project
} from './geo';

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

	// Spreading a bucket into Math.min throws RangeError above an engine limit: 65,536 in
	// Safari, about 125,000 in the Node this suite runs on — hence 200,000 here.
	it('handles a bucket of 200,000 points (a whole library taken in one place)', () => {
		const many = Array.from({ length: 200_000 }, (_, i) => ({
			id: i,
			lat: 48 + (i % 100) / 1000,
			lon: 2 + (i % 50) / 1000
		}));
		const [only, ...rest] = clusterPoints(many, view, 20, (n) => 2 * Math.sqrt(n));
		expect(rest).toEqual([]);
		expect(only.ids).toHaveLength(200_000);
		expect(only.bounds).toEqual({ south: 48, north: 48.099, west: 2, east: 2.049 });
	});

	it('returns nothing for no points', () => {
		expect(clusterPoints([], view, 10)).toEqual([]);
	});
});

describe('clustersInView', () => {
	it('keeps the clusters inside the window, plus a margin around it', () => {
		const at = (x: number, y: number) => ({
			x,
			y,
			ids: [x],
			bounds: { south: 0, north: 0, west: 0, east: 0 }
		});
		const all = [at(10, 10), at(104, 10), at(106, 10), at(50, 56), at(50, -6)];
		const seen = clustersInView(all, { x: 0, y: 0, w: 100, h: 50 }, 5);
		expect(seen.map((c) => c.ids[0])).toEqual([10, 104]);
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

describe('nearestCluster (the chosen dot, after the map has clustered again)', () => {
	const bounds = { south: 0, west: 0, north: 0, east: 0 };
	const clusters = [
		{ x: 10, y: 10, ids: [1, 2, 3], bounds },
		{ x: 12, y: 10, ids: [4], bounds },
		{ x: 200, y: 90, ids: [5, 6], bounds }
	];

	it('is the dot closest to where the choice was made', () => {
		expect(nearestCluster(clusters, { x: 10.4, y: 10 })?.ids).toEqual([1, 2, 3]);
		expect(nearestCluster(clusters, { x: 11.5, y: 10 })?.ids).toEqual([4]);
		expect(nearestCluster(clusters, { x: 190, y: 80 })?.ids).toEqual([5, 6]);
	});

	it('is nothing on an empty map', () => {
		expect(nearestCluster([], { x: 1, y: 1 })).toBeNull();
	});
});

const at = (lat: number, lon: number, id = 1) => ({ id, lat, lon });

describe('fitting the map to the photos', () => {
	it('frames every photo with a margin around them', () => {
		// France (lon 2, lat 46) and California (lon −122, lat 37): x 58…182, y 44…53
		const view = fitView([at(46, 2), at(37, -122, 2)], 2);
		expect(view.x).toBeLessThan(58);
		expect(view.x + view.w).toBeGreaterThan(182);
		expect(view.y).toBeLessThan(44);
		expect(view.y + view.w / 2).toBeGreaterThan(53);
	});
	it('the margin is a tenth of the photos’ spread on each side', () => {
		const view = fitView([at(0, -10), at(0, 10, 2)], 1, 0.1);
		expect(view.w).toBeCloseTo(24, 6); // 20 wide + 2 × 2
		expect(view.x).toBeCloseTo(168, 6);
	});
	it('keeps the frame’s own shape: a tall phone screen frames by height', () => {
		const view = fitView([at(60, 0), at(-60, 0, 2)], 0.5, 0.1);
		const height = view.w / 0.5;
		expect(height).toBeGreaterThanOrEqual(120 * 1.2 - 1e-9);
		expect(view.y).toBeLessThanOrEqual(30 - 12 + 1e-9);
	});
	it('one place, or photos all in one spot, zoom in no closer than the floor', () => {
		const view = fitView([at(48.85, 2.35), at(48.85, 2.35, 2)], 2);
		expect(view.w).toBe(MIN_VIEW);
		// centred on it
		expect(view.x + view.w / 2).toBeCloseTo(182.35, 6);
		expect(view.y + view.w / 4).toBeCloseTo(41.15, 6);
	});
	it('no photos: the whole world', () => {
		expect(fitView([], 2)).toEqual({ x: 0, y: 0, w: 360 });
	});
	it('photos on both sides of the world never ask for more than the world', () => {
		const view = fitView([at(80, -179), at(-80, 179, 2)], 2);
		expect(view).toEqual({ x: 0, y: 0, w: 360 });
	});
});

describe('keeping the view on the map', () => {
	it('stops at the edges of the world', () => {
		expect(clampView({ x: -50, y: -10, w: 100 }, 2)).toEqual({ x: 0, y: 0, w: 100 });
		expect(clampView({ x: 300, y: 170, w: 100 }, 2)).toEqual({ x: 260, y: 130, w: 100 });
	});
	it('zooms out no further than the world, and in no closer than the floor', () => {
		expect(clampView({ x: 0, y: 0, w: 900 }, 2).w).toBe(360);
		expect(clampView({ x: 10, y: 10, w: 0.01 }, 2).w).toBe(MIN_VIEW);
	});
	it('a frame taller than the world shows it whole, centred, with sea above and below', () => {
		const view = clampView({ x: 40, y: 0, w: 360 }, 0.5); // 720 high: four worlds of height
		expect(view.x).toBe(0);
		expect(view.y).toBe((180 - 720) / 2);
	});
});

describe('where a gesture leaves the view', () => {
	const view = { x: 100, y: 40, w: 60 };
	it('a drag to the right shows what was to the left', () => {
		// 10 px per degree: 50 px is 5 degrees
		expect(moved(view, { tx: 50, ty: -20, s: 1 }, 10)).toEqual({ x: 95, y: 42, w: 60 });
	});
	it('a pinch that doubles the picture halves the view, about where it was made', () => {
		// scaled ×2 about the frame's corner: the corner stays, the width halves
		expect(moved(view, { tx: 0, ty: 0, s: 2 }, 10)).toEqual({ x: 100, y: 40, w: 30 });
		// about the middle (300, 150 px): the middle of the view stays put
		const about = moved(view, { tx: -300, ty: -150, s: 2 }, 10);
		expect(about.x + about.w / 2).toBeCloseTo(view.x + view.w / 2, 6);
	});
	it('no gesture, no change', () => {
		expect(moved(view, { tx: 0, ty: 0, s: 1 }, 10)).toEqual(view);
	});
});
