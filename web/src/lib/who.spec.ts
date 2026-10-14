import { describe, expect, it } from 'vitest';
import { QUESTION_KEYS, without } from './questions';
import { WHO_AVAILABLE, chosenPerson, withPerson } from './who';

describe('the Who question', () => {
	it('is asked, now that the server filters by person', () => {
		expect(WHO_AVAILABLE).toBe(true);
	});
	it('reads the person chosen from the filters', () => {
		expect(chosenPerson({ person_id: [7] })).toBe(7);
		expect(chosenPerson({})).toBeUndefined();
	});
	it('chooses one person, replacing any other, and keeps the rest of the filters', () => {
		expect(withPerson({ year: 2019, person_id: [3] }, 7)).toEqual({ year: 2019, person_id: [7] });
	});
	it('takes the person away', () => {
		expect(withPerson({ year: 2019, person_id: [7] }, undefined)).toEqual({ year: 2019 });
	});
	it('is cleared with the rest of its question', () => {
		expect(without({ year: 2019, person_id: [7] }, QUESTION_KEYS.who)).toEqual({ year: 2019 });
	});
});
