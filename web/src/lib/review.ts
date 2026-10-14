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
