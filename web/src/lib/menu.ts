/** A row of a menu: a link (`href`) or an action (`run`). */
export type MenuItem = {
	label: string;
	href?: string;
	count?: number;
	/** What the count means, said aloud after the label: "4 photos". */
	countLabel?: string;
	current?: boolean;
	run?: () => void;
	/** An action that is a switch: whether it is on. */
	pressed?: boolean;
};
