/**
 * Editor geometry. The recipe is applied in this order (the backend renders the same way):
 *   1. quarter-turn `rotate` clockwise,
 *   2. flip in the rotated frame,
 *   3. `straighten` clockwise about the centre, zoomed just enough to leave no empty corners,
 *   4. `crop`, as fractions of that rotated frame.
 */
import type { CropRect, Recipe, Rotation } from './api/types';

export const RATIOS: { label: string; value: number | null }[] = [
	{ label: 'Free', value: null },
	{ label: '1:1', value: 1 },
	{ label: '4:5', value: 4 / 5 },
	{ label: '3:2', value: 3 / 2 },
	{ label: '16:9', value: 16 / 9 }
];

export const MIN_CROP = 0.05;
export const MAX_STRAIGHTEN = 15;

const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

export function rotatedAspect(aspect: number, rotate: Rotation): number {
	return rotate % 180 === 0 ? aspect : 1 / aspect;
}

/** Quarter turn clockwise (dir 1) or anticlockwise (-1); the crop turns with the picture. */
export function rotateRecipe(recipe: Recipe, dir: 1 | -1): Recipe {
	const rotate = (((recipe.rotate + dir * 90) % 360) + 360) % 360;
	const c = recipe.crop;
	const crop = !c
		? null
		: dir === 1
			? { x: 1 - c.y - c.h, y: c.x, w: c.h, h: c.w }
			: { x: c.y, y: 1 - c.x - c.w, w: c.h, h: c.w };
	return { ...recipe, rotate: rotate as Rotation, crop };
}

export function flipRecipe(recipe: Recipe, axis: 'h' | 'v'): Recipe {
	const c = recipe.crop;
	if (axis === 'h')
		return {
			...recipe,
			flip_horizontal: !recipe.flip_horizontal,
			crop: c && { ...c, x: 1 - c.x - c.w }
		};
	return { ...recipe, flip_vertical: !recipe.flip_vertical, crop: c && { ...c, y: 1 - c.y - c.h } };
}

/** Largest centred crop with pixel ratio `ratio` in an image of aspect `imageAspect`. */
export function centeredCrop(imageAspect: number, ratio: number): CropRect {
	if (ratio >= imageAspect) {
		const h = imageAspect / ratio;
		return { x: 0, y: (1 - h) / 2, w: 1, h };
	}
	const w = ratio / imageAspect;
	return { x: (1 - w) / 2, y: 0, w, h: 1 };
}

export function moveCrop(rect: CropRect, dx: number, dy: number): CropRect {
	return {
		...rect,
		x: clamp(rect.x + dx, 0, 1 - rect.w),
		y: clamp(rect.y + dy, 0, 1 - rect.h)
	};
}

export type Handle = 'nw' | 'ne' | 'sw' | 'se';

/**
 * Drag a corner by (dx, dy) fractions. The opposite corner stays put; with a fixed `ratio`
 * the width leads and the height follows, both shrunk together if they would leave the image.
 */
export function resizeCrop(
	rect: CropRect,
	handle: Handle,
	dx: number,
	dy: number,
	ratio: number | null,
	imageAspect: number
): CropRect {
	const west = handle === 'nw' || handle === 'sw';
	const north = handle === 'nw' || handle === 'ne';
	const anchorX = west ? rect.x + rect.w : rect.x;
	const anchorY = north ? rect.y + rect.h : rect.y;
	const roomX = west ? anchorX : 1 - anchorX;
	const roomY = north ? anchorY : 1 - anchorY;

	let w = clamp(rect.w + (west ? -dx : dx), MIN_CROP, roomX);
	let h = clamp(rect.h + (north ? -dy : dy), MIN_CROP, roomY);
	if (ratio !== null) {
		const hFor = (width: number) => (width * imageAspect) / ratio;
		h = hFor(w);
		if (h > roomY) {
			h = roomY;
			w = (h * ratio) / imageAspect;
		}
		if (h < MIN_CROP) {
			h = MIN_CROP;
			w = (h * ratio) / imageAspect;
		}
	}
	return { x: west ? anchorX - w : anchorX, y: north ? anchorY - h : anchorY, w, h };
}

/** Zoom needed so an image of `aspect` rotated by `degrees` still covers its own frame. */
export function coverScale(aspect: number, degrees: number): number {
	const t = (Math.abs(degrees) * Math.PI) / 180;
	if (t === 0) return 1;
	const cos = Math.cos(t);
	const sin = Math.sin(t);
	return Math.max(cos + sin / aspect, cos + sin * aspect);
}

/**
 * CSS transform for the editor stage. The <img> is centred (translate) in a stage shaped like
 * the rotated frame; transforms apply right to left: quarter turn, flip, zoom, straighten.
 */
export function previewTransform(recipe: Recipe, imageAspect: number): string {
	const frame = rotatedAspect(imageAspect, recipe.rotate);
	const zoom = coverScale(frame, recipe.straighten);
	const fx = recipe.flip_horizontal ? -1 : 1;
	const fy = recipe.flip_vertical ? -1 : 1;
	return `translate(-50%, -50%) rotate(${recipe.straighten}deg) scale(${+zoom.toFixed(4)}) scale(${fx}, ${fy}) rotate(${recipe.rotate}deg)`;
}

export function outputAspect(recipe: Recipe, imageAspect: number): number {
	const frame = rotatedAspect(imageAspect, recipe.rotate);
	return recipe.crop ? (recipe.crop.w * frame) / recipe.crop.h : frame;
}

export function isIdentity(recipe: Recipe): boolean {
	const c = recipe.crop;
	const fullCrop = !c || (c.x <= 0 && c.y <= 0 && c.w >= 1 && c.h >= 1);
	return (
		recipe.rotate === 0 &&
		!recipe.flip_horizontal &&
		!recipe.flip_vertical &&
		recipe.straighten === 0 &&
		fullCrop
	);
}
