import * as fs from "node:fs";
import * as path from "node:path";

export const WHOLE_ACCOUNT_TAG = "@whole-account";

const LOCK_DIR = path.resolve("e2e/.auth/account-lock");

const MUTEX = path.join(LOCK_DIR, "mutex");
const SHARED = path.join(LOCK_DIR, "shared");
const EXCLUSIVE = path.join(LOCK_DIR, "exclusive");
const POLL_MS = 250;

function pause(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function holders(): number[] {
  const pids = fs.readdirSync(SHARED).map(Number);
  for (const pid of pids.filter((pid) => !alive(pid))) {
    fs.rmSync(path.join(SHARED, String(pid)), { force: true });
  }
  return pids.filter(alive);
}

function exclusiveHolder(): number | null {
  if (!fs.existsSync(EXCLUSIVE)) return null;
  const pid = Number(fs.readFileSync(EXCLUSIVE, "utf8"));
  if (alive(pid)) return pid;
  fs.rmSync(EXCLUSIVE, { force: true });
  return null;
}

async function underMutex<T>(read: () => T): Promise<T> {
  for (;;) {
    try {
      fs.mkdirSync(MUTEX);
      break;
    } catch {
      await pause(20);
    }
  }
  try {
    return read();
  } finally {
    fs.rmdirSync(MUTEX);
  }
}

export function resetAccountLock(): void {
  fs.rmSync(LOCK_DIR, { recursive: true, force: true });
  fs.mkdirSync(SHARED, { recursive: true });
}

export async function holdShared(): Promise<() => Promise<void>> {
  const pid = process.pid;
  for (;;) {
    const held = await underMutex(() => {
      if (exclusiveHolder() !== null) return false;
      fs.writeFileSync(path.join(SHARED, String(pid)), "");
      return true;
    });
    if (held) break;
    await pause(POLL_MS);
  }
  return async () => {
    await underMutex(() => fs.rmSync(path.join(SHARED, String(pid)), { force: true }));
  };
}

export async function holdAlone(): Promise<() => Promise<void>> {
  const pid = process.pid;
  for (;;) {
    const held = await underMutex(() => {
      const owner = exclusiveHolder();
      if (owner !== null && owner !== pid) return false;
      fs.writeFileSync(EXCLUSIVE, String(pid));
      return holders().length === 0;
    });
    if (held) break;
    await pause(POLL_MS);
  }
  return async () => {
    await underMutex(() => fs.rmSync(EXCLUSIVE, { force: true }));
  };
}
