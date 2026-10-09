/** Photos and albums as the API sends them to one user. */
import type { AlbumSummary, AssetDetail, AssetOut } from '../src/lib/api/types.ts';
import { live, setFor, type AccessHelpers } from './access.ts';
import { editedSize } from './images.ts';
import type { MockAlbum, MockAsset, MockUser, World } from './types.ts';

export function shapeHelpers(h: World & AccessHelpers) {
	function toOut(user: MockUser, a: MockAsset): AssetOut {
		const size = editedSize(a);
		return {
			id: a.id,
			taken_at: a.taken_at,
			tz_offset_minutes: a.tz_offset_minutes,
			date_source: a.date_source,
			width: size.width,
			height: size.height,
			kind: a.kind,
			thumb: { url: `/api/assets/${a.id}/thumb?v=${a.edit_version}` },
			preview_ready: true,
			favourite: setFor(h.state().favourites, user.id).has(a.id),
			hidden: setFor(h.state().hidden, user.id).has(a.id),
			private: a.private_owner !== null,
			place: a.place ? { ...a.place.place } : null,
			edited: a.recipe !== null,
			variant_of: a.variant_of,
			group_id: a.group_id
		};
	}

	function toDetail(user: MockUser, a: MockAsset): AssetDetail {
		return {
			...toOut(user, a),
			byte_size: a.byte_size,
			mime_type: a.mime_type,
			camera_make: a.camera_make,
			camera_model: a.camera_model,
			latitude: a.place?.lat ?? null,
			longitude: a.place?.lon ?? null,
			imported_at: a.imported_at,
			origins: a.sources.map((s) => ({
				source_id: s.source_id,
				source_label: h.state().sources.find((x) => x.id === s.source_id)?.label ?? '?',
				relative_path: s.relative_path
			})),
			albums: h
				.state()
				.albums.filter((al) => al.items.includes(a.id) && h.albumRole(user, al))
				.map((al) => ({ id: al.id, title: al.title })),
			level: h.assetLevel(user, a) ?? 'view'
		};
	}

	function albumSummary(user: MockUser, album: MockAlbum): AlbumSummary {
		const items = album.items
			.map((id) => h.state().assets.find((a) => a.id === id && live(a)))
			.filter((a): a is MockAsset => !!a && h.assetLevel(user, a) !== null);
		const cover = items.find((a) => a.id === album.cover_asset_id) ?? items[0];
		return {
			id: album.id,
			title: album.title,
			description: album.description,
			cover: cover ? { url: `/api/assets/${cover.id}/thumb?v=${cover.edit_version}` } : null,
			count: items.length,
			owner_id: album.owner_id,
			role: h.albumRole(user, album) ?? 'viewer',
			updated_at: album.updated_at
		};
	}

	return { toOut, toDetail, albumSummary };
}
