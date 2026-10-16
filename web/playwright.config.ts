import { defineConfig, devices } from '@playwright/test';

/**
 * E2E against the mock API by default: `pnpm e2e` starts the mock (:8431) and a dev server
 * proxying /api to it (:5183). To run the same suite against a real backend, start it (with
 * a fresh data dir) and set E2E_BASE_URL (web app origin) and E2E_MOCK_URL='' — tests that
 * need to reset state then skip. See docs/wiring/web.md.
 */
const MOCK_PORT = Number(process.env.E2E_MOCK_PORT ?? 8431);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5183);
const external = !!process.env.E2E_BASE_URL;
const executablePath = process.env.PW_CHROMIUM || undefined;

export default defineConfig({
	testDir: 'e2e',
	fullyParallel: false,
	workers: 1, // one shared in-memory library, reset before each test
	retries: process.env.CI ? 1 : 0,
	timeout: 30_000,
	reporter: [['list']],
	use: {
		baseURL: process.env.E2E_BASE_URL ?? `http://127.0.0.1:${WEB_PORT}`,
		launchOptions: { executablePath },
		trace: 'retain-on-failure',
		// Tests change answers on their way to the page (`page.route`: withDetail, longLists, …).
		// Once the app's service worker controls the page, Chromium can send a request through it
		// and past the route, now and then: the real answer shows instead of the test's, a flake.
		// No test is about the service worker, so none runs.
		serviceWorkers: 'block'
	},
	projects: [
		{
			name: 'desktop',
			use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
		},
		{
			name: 'phone',
			use: {
				viewport: { width: 390, height: 844 },
				deviceScaleFactor: 2,
				isMobile: true,
				hasTouch: true,
				userAgent: devices['Pixel 7'].userAgent
			}
		}
	],
	webServer: external
		? undefined
		: [
				{
					command: `MOCK_PORT=${MOCK_PORT} node mock-api/server.ts`,
					url: `http://127.0.0.1:${MOCK_PORT}/api/health`,
					reuseExistingServer: false
				},
				{
					command: `PA_API=http://127.0.0.1:${MOCK_PORT} vite dev --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
					url: `http://127.0.0.1:${WEB_PORT}`,
					reuseExistingServer: false
				}
			]
});

export const MOCK_URL =
	process.env.E2E_MOCK_URL ?? (external ? '' : `http://127.0.0.1:${MOCK_PORT}`);
