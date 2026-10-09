/** The status line. */
export type NoticeAction = { label: string; run: () => void };

class Notice {
	text = $state('');
	action = $state<NoticeAction | null>(null);
	#timer: ReturnType<typeof setTimeout> | undefined;

	show(text: string, options: { ms?: number; action?: NoticeAction } = {}) {
		this.text = text;
		this.action = options.action ?? null;
		clearTimeout(this.#timer);
		this.#timer = setTimeout(
			() => {
				this.text = '';
				this.action = null;
			},
			options.ms ?? (options.action ? 8000 : 4000)
		);
	}

	/** Show a failure as the server's own sentence. */
	error(error: unknown) {
		this.show(error instanceof Error ? error.message : 'Something went wrong.', { ms: 7000 });
	}
}

export const notice = new Notice();
