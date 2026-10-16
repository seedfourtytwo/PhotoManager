/** Photos and albums as the API sends them to one user. */
import type { AlbumCover, AlbumSummary, AssetDetail, AssetOut } from '../src/lib/api/types.ts';
import { live, setFor, type AccessHelpers } from './access.ts';
import { editedSize, skyOf } from './images.ts';
import { displayName } from './names.ts';
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
			colour: skyOf(a),
			preview_ready: true,
			favourite: setFor(h.state().favourites, user.id).has(a.id),
			pinned: setFor(h.state().pinned, user.id).has(a.id),
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
			name: displayName(a, h.visible(user)),
			byte_size: a.byte_size,
			mime_type: a.mime_type,
			camera_make: a.camera_make,
			camera_model: a.camera_model,
			latitude: a.place?.lat ?? null,
			longitude: a.place?.lon ?? null,
			f_number: a.f_number,
			exposure_time: a.exposure_time,
			iso: a.iso,
			focal_length: a.focal_length,
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

	function albumCover(a: MockAsset): AlbumCover {
		const size = editedSize(a);
		return {
			asset_id: a.id,
			url: `/api/assets/${a.id}/thumb?v=${a.edit_version}`,
			preview_url: `/api/assets/${a.id}/preview?v=${a.edit_version}`,
			width: size.width,
			height: size.height
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
			cover: cover ? albumCover(cover) : null,
			count: items.length,
			owner_id: album.owner_id,
			role: h.albumRole(user, album) ?? 'viewer',
			updated_at: album.updated_at
		};
	}

	return { toOut, toDetail, albumSummary };
}
