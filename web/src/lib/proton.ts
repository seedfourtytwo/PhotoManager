/** Proton Drive places as the server names them, and how to say them to a person. */
export const PROTON_PHOTOS = '/photos';
export const PROTON_FILES = '/my-files';

/** "/my-files/Trips/2019" → "My files / Trips / 2019"; "/photos" → "Photos". */
export function protonPlaceName(path: string): string {
	if (path === PROTON_PHOTOS) return 'Photos';
	const inside = path.slice(PROTON_FILES.length).split('/').filter(Boolean);
	return ['My files', ...inside].join(' / ');
}
