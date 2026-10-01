/**
 * Synthetic "photos": a sky, a sun, hills or sea, drawn as SVG from a place palette and a seed.
 * The edit recipe is applied the same way the backend renders it (see src/lib/crop.ts).
 */
import type { Recipe } from '../src/lib/api/types.ts';
import { coverScale, rotatedAspect } from '../src/lib/crop.ts';
import { rng, type MockAsset } from './data.ts';

function mix(hex: string, other: string, t: number): string {
	const a = parseInt(hex.slice(1), 16);
	const b = parseInt(other.slice(1), 16);
	const ch = (shift: number) =>
		Math.round(((a >> shift) & 255) * (1 - t) + ((b >> shift) & 255) * t);
	return `#${((ch(16) << 16) | (ch(8) << 8) | ch(0)).toString(16).padStart(6, '0')}`;
}

function scene(asset: MockAsset, w: number, h: number): string {
	const r = rng(asset.seed);
	const sky = asset.place?.sky ?? '#a0a8b0';
	const ground = asset.place?.ground ?? '#6c6a60';
	const dusk = r.next() < 0.3;
	const top = dusk ? mix(sky, '#2a2440', 0.55) : mix(sky, '#ffffff', 0.25);
	const bottom = dusk ? mix(sky, '#f0a070', 0.5) : sky;
	const horizon = h * (0.5 + r.next() * 0.25);
	const sunX = w * (0.15 + r.next() * 0.7);
	const sunY = horizon * (0.25 + r.next() * 0.5);
	const sunR = Math.min(w, h) * (0.04 + r.next() * 0.05);
	const id = `g${asset.id}`;
	let land: string;
	if (asset.place?.sea) {
		land = `<rect x="0" y="${horizon}" width="${w}" height="${h - horizon}" fill="${ground}"/>
<rect x="0" y="${horizon}" width="${w}" height="${h * 0.006}" fill="${mix(ground, '#ffffff', 0.5)}"/>
<path d="M0 ${h} L0 ${horizon + (h - horizon) * 0.6} Q${w * 0.3} ${horizon + (h - horizon) * 0.4} ${w * 0.55} ${h} Z" fill="${mix('#d8c8a0', ground, 0.2)}"/>`;
	} else {
		const peak = (x: number, y: number) => `${x.toFixed(1)} ${y.toFixed(1)}`;
		const far = mix(ground, sky, 0.45);
		land = `<path d="M0 ${h} L0 ${peak(0, horizon)} Q${peak(w * 0.25, horizon - h * 0.12)} ${peak(w * 0.5, horizon)} T${peak(w, horizon - h * 0.05)} L${w} ${h} Z" fill="${far}"/>
<path d="M0 ${h} L0 ${peak(0, horizon + h * 0.1)} Q${peak(w * (0.3 + r.next() * 0.3), horizon - h * 0.05)} ${peak(w, horizon + h * 0.08)} L${w} ${h} Z" fill="${ground}"/>`;
	}
	return `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${top}"/><stop offset="1" stop-color="${bottom}"/></linearGradient></defs>
<rect width="${w}" height="${h}" fill="url(#${id})"/>
<circle cx="${sunX.toFixed(1)}" cy="${sunY.toFixed(1)}" r="${sunR.toFixed(1)}" fill="${dusk ? '#ffd9a0' : '#fff6de'}" opacity="0.9"/>
${land}`;
}

/** The photo as SVG, with the edit recipe applied unless `raw` (the editor's base image). */
export function renderAsset(asset: MockAsset, raw = false): string {
	const recipe: Recipe | null = raw ? null : asset.recipe;
	const aspect = asset.width / asset.height;
	const bw = 600;
	const bh = bw / aspect;
	if (!recipe) {
		return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${bw} ${bh.toFixed(1)}" width="${bw}" height="${bh.toFixed(0)}">${scene(asset, bw, bh)}</svg>`;
	}
	const frame = rotatedAspect(aspect, recipe.rotate);
	const fw = recipe.rotate % 180 === 0 ? bw : bh;
	const fh = fw / frame;
	const zoom = coverScale(frame, recipe.straighten);
	const fx = recipe.flip_horizontal ? -1 : 1;
	const fy = recipe.flip_vertical ? -1 : 1;
	const c = recipe.crop ?? { x: 0, y: 0, w: 1, h: 1 };
	const vb = [c.x * fw, c.y * fh, c.w * fw, c.h * fh].map((v) => v.toFixed(2)).join(' ');
	const transform = `translate(${fw / 2} ${fh / 2}) rotate(${recipe.straighten}) scale(${zoom}) scale(${fx} ${fy}) rotate(${recipe.rotate}) translate(${-bw / 2} ${-bh / 2})`;
	return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vb}" width="${(c.w * fw).toFixed(0)}" height="${(c.h * fh).toFixed(0)}"><g transform="${transform}">${scene(asset, bw, bh)}</g></svg>`;
}

/** Output pixel size after the recipe (what the thumb aspect becomes). */
export function editedSize(asset: MockAsset): { width: number; height: number } {
	const recipe = asset.recipe;
	if (!recipe) return { width: asset.width, height: asset.height };
	const quarter = recipe.rotate % 180 !== 0;
	const fw = quarter ? asset.height : asset.width;
	const fh = quarter ? asset.width : asset.height;
	const c = recipe.crop ?? { x: 0, y: 0, w: 1, h: 1 };
	return { width: Math.round(fw * c.w), height: Math.round(fh * c.h) };
}

/** A calm app icon: a sun over a horizon, drawn in ink on the background. */
export function iconSvg(size: number): string {
	return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}"><rect width="${size}" height="${size}" fill="#111"/><circle cx="${size * 0.5}" cy="${size * 0.46}" r="${size * 0.14}" fill="#ededed"/><rect x="${size * 0.18}" y="${size * 0.66}" width="${size * 0.64}" height="${size * 0.03}" fill="#ededed"/></svg>`;
}
