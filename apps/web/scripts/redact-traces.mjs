/**
 * Blank every VEuPathDB token and the e2e account's email and password in the
 * Playwright reports under a directory, inside nested zips too, before upload.
 *
 * Usage:
 *   node scripts/redact-traces.mjs blob-report
 */
import {
  existsSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { crc32, deflateRawSync, inflateRawSync } from "node:zlib";

export const REDACTED = "REDACTED";

/** A JWT whose header and payload are JSON objects, as every VEuPathDB token is. */
const JWT = /eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+/g;

const BINARY_EXTENSIONS = new Set([".png", ".jpeg", ".jpg", ".webm", ".gif"]);

const LOCAL_HEADER = 0x04034b50;
const CENTRAL_HEADER = 0x02014b50;
const END_OF_CENTRAL = 0x06054b50;
const STORED = 0;
const DEFLATED = 8;
const UTF8_NAMES = 0x0800;
const ZIP64_MARKER = 0xffffffff;
const DOS_DATE_1980 = 0x21;

/** A request body inside an action's params sits two JSON strings deep. */
const JSON_DEPTH = 3;

/** The account's email and password as a trace can hold them: raw, JSON-escaped, URL-encoded. */
export function accountSecrets(env) {
  const values = [env.WDK_TEST_EMAIL ?? "", env.WDK_TEST_PASSWORD ?? ""];
  const forms = values
    .filter((value) => value !== "")
    .flatMap((value) => {
      const escaped = [value];
      for (let depth = 0; depth < JSON_DEPTH; depth += 1) {
        escaped.push(JSON.stringify(escaped[depth]).slice(1, -1));
      }
      return [...escaped, encodeURIComponent(value)];
    });
  return [...new Set(forms)];
}

/** Read the entries of a zip from its central directory. Zip64 and encryption fail. */
export function readZip(zip) {
  const end = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (end < 0 || zip.readUInt32LE(end) !== END_OF_CENTRAL) {
    throw new Error("not a zip: no end of central directory");
  }
  const count = zip.readUInt16LE(end + 10);
  let at = zip.readUInt32LE(end + 16);
  if (at === ZIP64_MARKER) {
    throw new Error("zip64 archives are not supported");
  }
  const entries = [];
  for (let i = 0; i < count; i += 1) {
    if (zip.readUInt32LE(at) !== CENTRAL_HEADER) {
      throw new Error(`bad central directory header at ${at}`);
    }
    const flags = zip.readUInt16LE(at + 8);
    const method = zip.readUInt16LE(at + 10);
    const size = zip.readUInt32LE(at + 20);
    const nameLength = zip.readUInt16LE(at + 28);
    const skip = nameLength + zip.readUInt16LE(at + 30) + zip.readUInt16LE(at + 32);
    const offset = zip.readUInt32LE(at + 42);
    const name = zip.toString("utf8", at + 46, at + 46 + nameLength);
    if ((flags & 1) !== 0) {
      throw new Error(`encrypted entry ${name}`);
    }
    if (method !== STORED && method !== DEFLATED) {
      throw new Error(`entry ${name} uses compression method ${method}`);
    }
    if (size === ZIP64_MARKER || offset === ZIP64_MARKER) {
      throw new Error("zip64 archives are not supported");
    }
    const dataStart =
      offset + 30 + zip.readUInt16LE(offset + 26) + zip.readUInt16LE(offset + 28);
    const raw = zip.subarray(dataStart, dataStart + size);
    entries.push({
      name,
      method,
      time: zip.readUInt16LE(at + 12),
      date: zip.readUInt16LE(at + 14),
      data: method === DEFLATED ? inflateRawSync(raw) : Buffer.from(raw),
    });
    at += 46 + skip;
  }
  return entries;
}

/** Write entries as a zip; each keeps its compression method and timestamp. */
export function writeZip(entries) {
  const locals = [];
  const centrals = [];
  let offset = 0;
  for (const {
    name,
    data,
    method = DEFLATED,
    time = 0,
    date = DOS_DATE_1980,
  } of entries) {
    const nameBytes = Buffer.from(name, "utf8");
    const body = method === DEFLATED ? deflateRawSync(data) : data;
    const fields = Buffer.alloc(16);
    fields.writeUInt16LE(time, 0);
    fields.writeUInt16LE(date, 2);
    fields.writeUInt32LE(crc32(data), 4);
    fields.writeUInt32LE(body.length, 8);
    fields.writeUInt32LE(data.length, 12);

    const local = Buffer.alloc(30);
    local.writeUInt32LE(LOCAL_HEADER, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(UTF8_NAMES, 6);
    local.writeUInt16LE(method, 8);
    fields.copy(local, 10);
    local.writeUInt16LE(nameBytes.length, 26);
    locals.push(local, nameBytes, body);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(CENTRAL_HEADER, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(UTF8_NAMES, 8);
    central.writeUInt16LE(method, 10);
    fields.copy(central, 12);
    central.writeUInt16LE(nameBytes.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBytes);
    offset += local.length + nameBytes.length + body.length;
  }
  const directory = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(END_OF_CENTRAL, 0);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

/** Blank every token and every secret in the bytes. Latin-1 maps each byte to one char. */
function redactBytes(bytes, secrets) {
  let text = bytes.toString("latin1").replace(JWT, REDACTED);
  const needles = secrets
    .map((secret) => Buffer.from(secret, "utf8").toString("latin1"))
    .sort((a, b) => b.length - a.length);
  for (const needle of needles) {
    text = text.split(needle).join(REDACTED);
  }
  const redacted = Buffer.from(text, "latin1");
  return redacted.equals(bytes) ? null : redacted;
}

/** The redacted bytes of one file, or null when it holds nothing to redact. */
export function redactFile(name, bytes, secrets) {
  const extension = path.extname(name).toLowerCase();
  if (BINARY_EXTENSIONS.has(extension)) {
    return null;
  }
  if (extension !== ".zip") {
    return redactBytes(bytes, secrets);
  }
  const entries = readZip(bytes);
  let changed = false;
  const redacted = entries.map((entry) => {
    const data = redactFile(entry.name, entry.data, secrets);
    if (data === null) {
      return entry;
    }
    changed = true;
    return { ...entry, data };
  });
  return changed ? writeZip(redacted) : null;
}

/** Redact every file under the directory in place; return the paths rewritten. */
export function redactDirectory(dir, secrets) {
  if (!existsSync(dir)) {
    return [];
  }
  const rewritten = [];
  const files = readdirSync(dir, { recursive: true })
    .map((relative) => path.join(dir, relative))
    .filter((file) => statSync(file).isFile())
    .sort();
  for (const file of files) {
    const redacted = redactFile(file, readFileSync(file), secrets);
    if (redacted !== null) {
      writeFileSync(file, redacted);
      rewritten.push(file);
    }
  }
  return rewritten;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const dir = process.argv[2];
  if (dir === undefined) {
    console.error("usage: node scripts/redact-traces.mjs <report directory>");
    process.exit(2);
  }
  const rewritten = redactDirectory(dir, accountSecrets(process.env));
  console.log(`Redacted ${rewritten.length} file(s) under ${dir}`);
}
