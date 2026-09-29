export async function fetchHealth(fetcher: typeof fetch = fetch) {
	const response = await fetcher('/api/health');
	if (!response.ok) throw new Error(`health check failed: ${response.status}`);
	return (await response.json()) as { status: string; version: string };
}
