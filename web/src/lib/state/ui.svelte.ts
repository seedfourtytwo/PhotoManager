/** The viewport's width class. */
class Viewport {
	width = $state(typeof window === 'undefined' ? 1440 : window.innerWidth);
	get phone() {
		return this.width < 640;
	}
	get desktop() {
		return this.width >= 1024;
	}
}

export const viewport = new Viewport();
if (typeof window !== 'undefined')
	window.addEventListener('resize', () => (viewport.width = window.innerWidth));
