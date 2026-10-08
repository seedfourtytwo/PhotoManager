import { defineConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		// PA_API points the dev server at another API, e.g. the mock (pnpm mock) on :8421.
		proxy: { '/api': process.env.PA_API ?? 'http://127.0.0.1:8420' }
	},
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'client',
					browser: {
						enabled: true,
						provider: playwright({
							// CI/containers can point at a preinstalled Chromium instead of downloading one.
							launchOptions: process.env.PW_CHROMIUM
								? { executablePath: process.env.PW_CHROMIUM }
								: {}
						}),
						instances: [{ browser: 'chromium', headless: true }]
					},
					include: ['src/**/*.svelte.{test,spec}.{js,ts}'],
					exclude: ['src/lib/server/**']
				}
			},

			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					// Vitest blanks CSS by default; the style tests read every stylesheet under src as text.
					css: { include: [/src\/.*\.css/] },
					include: ['src/**/*.{test,spec}.{js,ts}', 'mock-api/**/*.spec.ts'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
