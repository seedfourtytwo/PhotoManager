/** Why a photo waits for review, said to a person. */
const TITLES: Record<string, [many: string, one: string]> = {
	lookalike: ['Look like photos you already have', 'A look-alike'],
	screenshot: ['Screenshots', 'A screenshot'],
	document: ['Documents', 'A document'],
	receipt: ['Receipts', 'A receipt'],
	meme: ['Memes', 'A meme']
};

/** A group's heading: "Screenshots". */
export function reviewTitle(reason: string): string {
	return TITLES[reason]?.[0] ?? 'Other';
}

/** One photo's sheet: "A screenshot". */
export function reviewOne(reason: string): string {
	return TITLES[reason]?.[1] ?? 'Held back';
}

type Sized = { width: number | null; height: number | null };
const pixels = (a: Sized) => (a.width && a.height ? a.width * a.height : 0);

/** "4032 × 3024 · 12 MP": what a look-alike's size chip says; '' when the size is not known. */
export function sizeLine(a: Sized): string {
	const n = pixels(a);
	if (!n) return '';
	const mp = n / 1e6;
	return `${a.width} × ${a.height} · ${mp >= 10 ? Math.round(mp) : Math.round(mp * 10) / 10} MP`;
}

/** Which of two photos has more pixels, or null when they are the same or a size is unknown. */
export function largerOf(first: Sized, second: Sized): 'first' | 'second' | null {
	const [a, b] = [pixels(first), pixels(second)];
	if (!a || !b || a === b) return null;
	return a > b ? 'first' : 'second';
}
