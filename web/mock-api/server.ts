/**
 * Mock API server: `pnpm mock` (port 8421). Point the dev server at it with
 * PA_API=http://127.0.0.1:8421 (the scripts do this for you).
 *   MOCK_USERS=none   start with no accounts, to see the first-run screen
 *   MOCK_COUNT=10000  generate a bigger library (performance checks)
 */
import { createServer } from 'node:http';
import { createMockApi } from './app.ts';
import { makeState } from './data.ts';

const port = Number(process.env.MOCK_PORT ?? 8421);
const users = process.env.MOCK_USERS === 'none' ? 'none' : 'seed';
const count = Number(process.env.MOCK_COUNT ?? 300);
const api = createMockApi(makeState({ users, count }));

createServer((req, res) => void api.handle(req, res)).listen(port, '127.0.0.1', () => {
	console.log(`mock API on http://127.0.0.1:${port} (${count} photos, users: ${users})`);
	if (users === 'seed') console.log('sign in as admin / correct horse');
});
