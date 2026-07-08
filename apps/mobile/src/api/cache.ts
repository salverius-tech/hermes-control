export type CacheStorage = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
};

export async function readCache<T>(storage: CacheStorage, key: string): Promise<T | null> {
  try {
    const value = await storage.getItem(key);
    if (!value) return null;
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

export async function writeCache<T>(storage: CacheStorage, key: string, value: T): Promise<void> {
  try {
    await storage.setItem(key, JSON.stringify(value));
  } catch {
    // Cache writes are best-effort and should never break live API flows.
  }
}
