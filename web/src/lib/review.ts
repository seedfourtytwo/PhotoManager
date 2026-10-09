/** Why a photo waits for review, said to a person. */
const TITLES: Record<string, string> = {
	lookalike: 'Look like photos you already have',
	screenshot: 'Screenshots',
	document: 'Documents',
	receipt: 'Receipts',
	meme: 'Memes'
};

export function reviewTitle(reason: string): string {
	return TITLES[reason] ?? 'Other';
}
