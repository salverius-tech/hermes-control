export function buildApiUrl(apiUrl: string, path: string): string {
  const base = apiUrl.replace(/\/+$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  return `${base}${suffix}`;
}

export function buildWebSocketUrl(apiUrl: string, token: string): string {
  const url = new URL(buildApiUrl(apiUrl, '/ws/events'));
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${url.toString()}?token=${encodeURIComponent(token)}`;
}
