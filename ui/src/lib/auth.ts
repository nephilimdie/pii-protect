const KEY_NAME = "pii_protect_api_key";

export function saveKey(key: string): void {
  localStorage.setItem(KEY_NAME, key);
}

export function getKey(): string | null {
  return localStorage.getItem(KEY_NAME);
}

export function clearKey(): void {
  localStorage.removeItem(KEY_NAME);
}
