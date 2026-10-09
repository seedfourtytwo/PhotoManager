/** The machine the mock runs on: its disks, its folders and the Proton Drive it is signed in to. */
import { HttpError } from './http.ts';
import type { World } from './types.ts';

/** The mock machine: one roomy disk, one too small, one cloud remote. */
export const LIBRARY_BYTES = 38_400_000_000;
export const DISKS = [
	{ path: '/media/c/Tiny stick', label: 'Tiny stick', free_bytes: 2_000_000_000 },
	{ path: '/media/c/USB disk', label: 'USB disk', free_bytes: 500_000_000_000 }
];
export const REMOTES = ['proton'];

/** The mock machine's folders. Any other full path opens as an empty folder, unless its
 *  name says it is missing. */
const HOME = '/home/c';
const TREE: Record<string, string[]> = {
	[HOME]: ['Documents', 'Pictures', 'Scans'],
	[`${HOME}/Pictures`]: ['2019', '2020'],
	'/media/c/USB disk': ['DCIM']
};

export function machineHelpers(h: World) {
	function listFolders(asked: string | undefined) {
		const path = (asked ?? HOME).replace(/(?<=.)\/+$/, '');
		if (!path.startsWith('/'))
			throw new HttpError(422, 'give the full path of the folder, starting with /');
		if (path.includes('missing') && !h.state().createdFolders.has(path))
			throw new HttpError(404, `folder not found on this machine: ${path}`);
		const added = h.state().sources.find((s) => s.kind === 'folder' && s.path === path);
		return {
			path,
			parent: path === '/' ? null : path.slice(0, path.lastIndexOf('/')) || '/',
			folders: (TREE[path] ?? []).map((name) => ({ name, path: `${path}/${name}` })),
			truncated: false,
			roots: [{ label: 'Home', path: HOME }, ...DISKS.map((d) => ({ label: d.label, path: d.path }))], // prettier-ignore
			source_problem: added
				? `already added as “${added.label}”`
				: path === HOME
					? 'this folder contains the photo library itself'
					: null
		};
	}

	/** Same answers as the real routes: 422 for a place that may not be read, 404 when gone. */
	function protonPlace(path: string, photosToo: boolean) {
		const inFiles = path === '/my-files' || path.startsWith('/my-files/');
		if (!(inFiles || (photosToo && path === '/photos')) || path.split('/').includes('..'))
			throw new HttpError(
				422,
				'choose the Photos section (/photos) or a folder in My files (/my-files/...)'
			);
		if (inFiles && !(path in h.state().protonTree))
			throw new HttpError(404, `folder '${path}' not found on Proton Drive`);
	}

	return { listFolders, protonPlace };
}
