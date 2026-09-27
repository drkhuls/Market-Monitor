import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "data");

export async function readJson<T>(name: string, fallback: T): Promise<T> {
  try {
    const raw = await readFile(path.join(DATA_DIR, name), "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export async function writeJson(name: string, value: unknown): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true });
  const target = path.join(DATA_DIR, name);
  const temporary = `${target}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`);
  await rename(temporary, target);
}
