/** Reads the custom properties of each rule in a stylesheet, for the theme tests. */

const squash = (text: string) => text.replace(/\s+/g, ' ').trim();

/** Key: enclosing at-rules and the selector, joined by " | ". Value: its `--name: value` pairs. */
export function readBlocks(css: string): Map<string, Record<string, string>> {
	const blocks = new Map<string, Record<string, string>>();
	const path: string[] = [];
	let text = '';
	for (const char of css.replace(/\/\*[\s\S]*?\*\//g, '')) {
		if (char === '{') {
			path.push(squash(text));
			text = '';
		} else if (char === '}') {
			const found: Record<string, string> = {};
			for (const declaration of text.split(';')) {
				const colon = declaration.indexOf(':');
				const name = declaration.slice(0, colon).trim();
				if (colon > 0 && name.startsWith('--')) found[name] = squash(declaration.slice(colon + 1));
			}
			if (Object.keys(found).length > 0) blocks.set(path.join(' | '), found);
			path.pop();
			text = '';
		} else text += char;
	}
	return blocks;
}
