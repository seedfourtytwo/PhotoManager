/**
 * An image that shows once it is decoded, so it fades in whole instead of painting in: the
 * attachment marks it `data-in`, which the stylesheet turns into opacity 1.
 */
export function fadeIn(img: HTMLImageElement) {
	const show = () =>
		void img
			.decode()
			.catch(() => undefined)
			.then(() => (img.dataset.in = ''));
	if (img.complete && img.naturalWidth) show();
	else img.addEventListener('load', show, { once: true });
}
