import { api } from "./run";

export interface Preferences {
  voice: string;
  length_minutes: number;
  no_spoiler: boolean;
  tone: string;
  image_style: string;
}

export interface MemoryItem {
  key: string;
  [field: string]: unknown;
}

export interface Memory {
  preferences: Preferences;
  books: MemoryItem[];
  characters: MemoryItem[];
  feedback: MemoryItem[];
}

export const getMemory = (token: string) => api<Memory>("/me/memory", token);

export const savePreferences = (token: string, prefs: Partial<Preferences>) =>
  api<Memory>("/me/memory/preferences", token, { method: "PUT", body: JSON.stringify(prefs) });

export const deleteMemory = (token: string) =>
  api<{ deleted: number }>("/me/memory", token, { method: "DELETE" });
