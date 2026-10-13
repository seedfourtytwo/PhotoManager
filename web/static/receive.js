// @ts-check
/**
 * The receiving page of "Send to a device" (receive.html). Plain script on purpose: the page
 * loads nothing of the app and runs under a policy that allows only this file.
 *
 * The token is the part of the link after '#'. It only ever leaves in the body of a POST:
 * first to ask what waits (which uses nothing up), then, on the tap, to collect the photos.
 */
(function () {
	const LOOK = '/api/handovers/look';
	const COLLECT = '/api/handovers/collect';
	const token = location.hash.slice(1);
	/** @param {string} id */
	const el = (id) => /** @type {HTMLElement} */ (document.getElementById(id));
	const title = el('title');
	const line = el('line');
	const facts = el('facts');
	const after = el('after');
	const button = /** @type {HTMLButtonElement} */ (el('download'));
	/** @type {ReturnType<typeof setTimeout> | undefined} */
	let runsOut;

	/** @param {string} text */
	const sentence = (text) => text.charAt(0).toUpperCase() + text.slice(1) + '.';

	/** Nothing more can be done here: say why. @param {string} heading @param {string} text */
	function finish(heading, text) {
		clearTimeout(runsOut);
		title.textContent = heading;
		line.textContent = text;
		facts.hidden = button.hidden = after.hidden = true;
	}

	/** @param {string} text @param {boolean} [warn] */
	function fact(text, warn) {
		const item = document.createElement('li');
		item.textContent = text;
		if (warn) item.className = 'warn';
		facts.append(item);
	}

	/** A refusal, in the server's own sentence. @param {string} text @param {number} [status] */
	function refused(text, status) {
		let detail = '';
		try {
			detail = JSON.parse(text).detail;
		} catch {
			// not JSON: something else answered in the server's place
		}
		if (typeof detail !== 'string' || !detail) return finish('This link could not be opened', unreachable);
		const wait = status === 429 || detail.startsWith('too many');
		finish(wait ? 'Please wait' : 'This link does not work', sentence(detail));
	}
	const unreachable =
		'The photo library could not be reached. Check that this device is on the same network ' +
		'as the person sending, then open the link again.';

	/** @param {{count: number, sent_by: string, expires_at: string, encrypted: boolean, details_removed: boolean}} waiting */
	function show(waiting) {
		const what = waiting.count === 1 ? '1 photo' : waiting.count + ' photos';
		title.textContent = waiting.sent_by + ' is sending you ' + what;
		line.textContent =
			waiting.count === 1 ? 'It arrives as one picture file.' : 'They arrive together as one ZIP file.';
		facts.replaceChildren();
		if (!waiting.encrypted)
			fact(
				'Not encrypted: others on this network could see these photos while they travel.',
				true
			);
		fact(
			waiting.details_removed
				? 'Location, camera details and file names were removed.'
				: 'The photos keep their location, camera details and file names.'
		);
		const until = new Date(waiting.expires_at);
		const time = until.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		fact('The link works once, until ' + time + '.');
		facts.hidden = button.hidden = false;
		const left = until.getTime() - Date.now();
		runsOut = setTimeout(
			() => finish('This link has run out', 'Ask the person sending for a new one.'),
			Math.max(left, 0)
		);
	}

	/** Post the token as a real form into a hidden frame: the browser saves the stream itself. */
	function collect() {
		button.disabled = true;
		clearTimeout(runsOut);
		const frame = document.createElement('iframe');
		frame.name = 'receive-download';
		frame.title = 'Download';
		frame.hidden = true;
		frame.addEventListener('load', () => {
			// a saved file never loads the frame; a refusal does, with the server's answer
			let text;
			try {
				text = frame.contentDocument?.body?.innerText ?? '';
			} catch {
				text = '?'; // a browser's own error page: the server did not answer
			}
			if (text.trim()) refused(text); // empty: the new frame itself
		});
		document.body.append(frame);
		const form = document.createElement('form');
		form.method = 'POST';
		form.action = COLLECT;
		form.target = frame.name;
		form.hidden = true;
		const field = document.createElement('input');
		field.type = 'hidden';
		field.name = 'token';
		field.value = token;
		form.append(field);
		document.body.append(form);
		form.submit();
		form.remove();
		// the link is used up: it need not stay in the address bar or the history
		history.replaceState(null, '', location.pathname);
		title.textContent = 'Your download has started';
		line.textContent = 'This link is now used up. You can close this page.';
		facts.hidden = button.hidden = true;
		after.textContent =
			'Look in your downloads (on an iPhone: the Files app). Nothing arrived? Ask for a new link.';
		after.hidden = false;
	}

	async function open() {
		if (!token) {
			finish('This link is incomplete', 'Scan the code or open the link again, whole.');
			return;
		}
		let response;
		try {
			response = await fetch(LOOK, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ token }),
				cache: 'no-store',
				referrerPolicy: 'no-referrer'
			});
		} catch {
			finish('This link could not be opened', unreachable);
			return;
		}
		if (!response.ok) {
			refused(await response.text(), response.status);
			return;
		}
		show(await response.json());
	}

	button.addEventListener('click', collect);
	void open();
})();
