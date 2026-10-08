import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import type { BackupHealth, BackupProblem } from '$lib/api';
import BackupBanner from './BackupBanner.svelte';

const health = (problems: BackupHealth['problems']): BackupHealth => ({
	protected: false,
	places_ok: 0,
	places_total: 1,
	problems
});
const alert: BackupProblem = {
	severity: 'alert',
	message: 'Home server: the last backup failed.',
	target_id: 1
};
const warning: BackupProblem = {
	severity: 'warning',
	message: 'Only one backup place is set up.',
	target_id: null
};

describe('BackupBanner', () => {
	it('renders nothing without health or without problems', async () => {
		const { container } = render(BackupBanner, { health: null });
		expect(container.querySelector('p')).toBeNull();
		const empty = render(BackupBanner, { health: health([]) });
		expect(empty.container.querySelector('p')).toBeNull();
	});

	it('shows the first problem and counts the rest', async () => {
		render(BackupBanner, { health: health([alert, warning, warning]) });
		const banner = page.getByRole('alert');
		await expect.element(banner).toHaveTextContent(/Home server: the last backup failed\./);
		await expect.element(banner).toHaveTextContent('· and 2 more');
	});

	it('says nothing about others when there is one problem', async () => {
		render(BackupBanner, { health: health([warning]) });
		await expect.element(page.getByRole('status')).not.toHaveTextContent('more');
	});

	it('is an alert for an alert and a status for a warning', async () => {
		render(BackupBanner, { health: health([warning, alert]) });
		await expect.element(page.getByRole('status')).toBeInTheDocument();
		expect(page.getByRole('alert').elements()).toHaveLength(0);
	});

	it('links to the backups section and cannot be dismissed', async () => {
		render(BackupBanner, { health: health([alert]) });
		await expect
			.element(page.getByRole('link', { name: 'Backups' }))
			.toHaveAttribute('href', '/admin#a-backups');
		expect(page.getByRole('button').elements()).toHaveLength(0);
	});
});
