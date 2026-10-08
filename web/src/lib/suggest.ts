/**
 * A name field that fills itself in from a choice (the folder picked): the returned function
 * gives what the field should hold now. It follows the latest suggestion for as long as the
 * field still holds the previous one, and leaves alone a name the user typed.
 */
export function suggester(): (current: string, suggestion: string) => string {
	let suggested = '';
	return (current, suggestion) => {
		const next = current === suggested ? suggestion : current;
		suggested = suggestion;
		return next;
	};
}
