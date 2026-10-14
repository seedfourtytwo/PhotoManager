/** Who may see what: folder access, album roles, and the lookups that apply them. */
import type { AlbumSummary, Level } from '../src/lib/api/types.ts';
import { HttpError, idParam, me, type Ctx } from './http.ts';
import type { MockAlbum, MockAsset, MockUser, World } from './types.ts';

const LEVELS: Level[] = ['view', 'download', 'edit'];
export const rank = (level: Level | null) => (level ? LEVELS.indexOf(level) : -1);
const maxLevel = (a: Level | null, b: Level | null) => (rank(a) >= rank(b) ? a : b);

/** In the library: not in the trash, not held for review. */
export const live = (a: MockAsset) => a.trashed_at === null && a.held === null;

export const setFor = (map: Map<number, Set<number>>, userId: number) => {
	if (!map.has(userId)) map.set(userId, new Set());
	return map.get(userId)!;
};

export function accessHelpers(h: World) {
	function sourceLevel(user: MockUser, sourceId: number): Level | null {
		if (user.role === 'admin') return 'edit';
		const access = h.state().access.get(sourceId);
		const source = h.state().sources.find((s) => s.id === sourceId);
		if (!access || !source || !source.enabled) return null;
		let level: Level | null = source.owner_id === user.id ? 'edit' : access.everyone;
		for (const entry of access.users)
			if (entry.user_id === user.id) level = maxLevel(level, entry.level);
		return level;
	}

	function albumRole(user: MockUser, album: MockAlbum): AlbumSummary['role'] | null {
		if (album.owner_id === user.id) return 'owner';
		if (user.role === 'admin') return 'editor';
		return album.members.find((m) => m.user_id === user.id)?.role ?? null;
	}

	function assetLevel(user: MockUser, asset: MockAsset): Level | null {
		if (asset.private_owner !== null && asset.private_owner !== user.id) return null;
		let level: Level | null = null;
		for (const s of asset.sources) level = maxLevel(level, sourceLevel(user, s.source_id));
		for (const album of h.state().albums) {
			if (!album.items.includes(asset.id)) continue;
			const role = albumRole(user, album);
			// Albums grant view only; downloading and editing come from folder access.
			if (role) level = maxLevel(level, 'view');
		}
		if (user.role === 'guest' && level === 'edit') level = 'download';
		return level;
	}

	function visible(user: MockUser): MockAsset[] {
		return h.state().assets.filter((a) => live(a) && assetLevel(user, a) !== null);
	}

	const heldFor = (user: MockUser) =>
		h
			.state()
			.assets.filter(
				(a) => a.trashed_at === null && a.held !== null && assetLevel(user, a) !== null
			);

	function findAsset(user: MockUser, id: number): MockAsset {
		const asset = h.state().assets.find((a) => a.id === id && live(a));
		if (!asset || assetLevel(user, asset) === null) throw new HttpError(404, 'Photo not found.');
		return asset;
	}

	function needLevel(user: MockUser, asset: MockAsset, level: Level) {
		if (rank(assetLevel(user, asset)) < rank(level))
			throw new HttpError(403, `You need “${level}” access to this photo.`);
	}

	function findAlbum(ctx: Ctx, minimum: 'viewer' | 'editor' | 'owner' = 'viewer'): MockAlbum {
		const album = h.state().albums.find((a) => a.id === idParam(ctx));
		const role = album ? albumRole(me(ctx), album) : null;
		if (!album || !role) throw new HttpError(404, 'Album not found.');
		const order = ['viewer', 'editor', 'owner'];
		const effective = me(ctx).role === 'admin' ? 'owner' : role;
		if (order.indexOf(effective) < order.indexOf(minimum))
			throw new HttpError(403, `You need to be the album's ${minimum}.`);
		return album;
	}

	return {
		albumRole,
		assetLevel,
		sourceLevel,
		visible,
		heldFor,
		findAsset,
		needLevel,
		findAlbum
	};
}
export type AccessHelpers = ReturnType<typeof accessHelpers>;
