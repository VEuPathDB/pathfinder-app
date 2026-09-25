/** Fails a banned synonym from the vocabulary lexicon in text a researcher or the model reads. */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LEXICON = "docs/knowledge/conventions/vocabulary.md";

// The web app's own compiler parses its source, so JSX text is exact.
const ts = createRequire(join(ROOT, "apps/web/package.json"))("typescript");

const WEB_TREES = ["apps/web/src"];
const MODEL_TREES = [
  "apps/api/src/pathfinder/ai",
  "apps/api/src/pathfinder/assistants",
];
const DETAIL_TREES = [
  "apps/api/src/pathfinder/transport",
  "apps/api/src/pathfinder/services",
];
const SKIPPED = new Set([
  "node_modules",
  "__pycache__",
  "generated",
  "tests",
  "__tests__",
  "test",
  "typings",
]);
const TEST_FILE = /\.(test|spec)\.tsx?$|(^|\/)test_[^/]*\.py$|(^|\/)conftest\.py$/;

// ---------------------------------------------------------------- lexicon

function tableRows(lines, start) {
  const rows = [];
  for (let i = start; i < lines.length && lines[i].trim().startsWith("|"); i += 1) {
    rows.push(
      lines[i]
        .trim()
        .replace(/^\||\|$/g, "")
        .split("|")
        .map((cell) => cell.trim()),
    );
  }
  return rows;
}

function tablesIn(markdown) {
  const lines = markdown.split("\n");
  const tables = [];
  for (let i = 0; i < lines.length; i += 1) {
    const isHeader =
      lines[i].trim().startsWith("|") &&
      i + 1 < lines.length &&
      /^\|[\s|:-]+\|$/.test(lines[i + 1].trim());
    if (!isHeader) continue;
    const [header, , ...body] = tableRows(lines, i);
    tables.push({ header: header.map((h) => h.toLowerCase()), body });
    i += body.length + 1;
  }
  return tables;
}

const unquote = (cell) => cell.replace(/`/g, "").trim();

// "researcher" rows read what a researcher sees; "all" rows read the model's text too.
const SCOPES = new Set(["all", "researcher"]);

export function parseLexicon(markdown) {
  const tables = tablesIn(markdown);
  const lexicon = tables.find((t) => t.header.some((h) => h.startsWith("banned")));
  if (!lexicon)
    throw new Error("vocabulary.md has no lexicon table (a 'Banned synonyms' column)");
  const column = (table, prefix) => table.header.findIndex((h) => h.startsWith(prefix));
  const [concept, name, banned, scope] = ["concept", "name", "banned", "scope"].map(
    (c) => column(lexicon, c),
  );
  const rows = lexicon.body.map((cells) => {
    const reach = unquote(cells[scope] ?? "all");
    if (!SCOPES.has(reach))
      throw new Error(`vocabulary.md: scope "${reach}" is not all or researcher`);
    return {
      concept: cells[concept],
      name: unquote(cells[name]),
      banned: cells[banned]
        .split(",")
        .map(unquote)
        .filter((word) => word && word !== "-"),
      scope: reach,
    };
  });
  const exempt = tables.find(
    (t) => t.header.includes("synonym") && t.header.includes("path"),
  );
  const exemptions = exempt
    ? exempt.body.map((cells) => ({
        synonym: unquote(cells[column(exempt, "synonym")]),
        path: unquote(cells[column(exempt, "path")]),
        reason: cells[column(exempt, "reason")],
      }))
    : [];
  const raw = tables.find((t) => t.header.includes("identifier"));
  const rawValues = raw
    ? raw.body.map((cells) => ({
        identifier: unquote(cells[column(raw, "identifier")]),
        name: unquote(cells[column(raw, "name")]),
        reason: cells[column(raw, "reason")],
      }))
    : [];
  return { rows, exemptions, rawValues };
}

// ------------------------------------------------------------------- web

const COPY_NAMES = new Set([
  "head",
  "label",
  "title",
  "aria-label",
  "aria-description",
  "placeholder",
  "description",
  "alt",
  "tooltip",
  "heading",
  "subtitle",
  "message",
  "hint",
  "summary",
  "caption",
]);
const CODE_NAMES = new Set([
  "className",
  "class",
  "id",
  "key",
  "href",
  "src",
  "role",
  "type",
  "name",
  "htmlFor",
  "variant",
  "size",
  "queryKey",
  "testId",
]);
const CODE_CALLEES =
  /^(cn|clsx|cva|twMerge|require|fetch|console\.\w+|document\.\w+|new URL)$/;
const PROSE = /[A-Za-z][.,:;!?'")]*\s+["'(]*[A-Za-z]/;

function isTransparent(node, child) {
  if (ts.isParenthesizedExpression(node) || ts.isJsxExpression(node)) return true;
  if (ts.isAsExpression(node) || ts.isSatisfiesExpression(node)) return true;
  if (ts.isTemplateSpan(node) || ts.isTemplateExpression(node)) return true;
  if (ts.isConditionalExpression(node)) return child !== node.condition;
  if (ts.isBinaryExpression(node)) {
    const op = node.operatorToken.kind;
    return (
      op === ts.SyntaxKind.PlusToken ||
      op === ts.SyntaxKind.QuestionQuestionToken ||
      op === ts.SyntaxKind.BarBarToken ||
      op === ts.SyntaxKind.AmpersandAmpersandToken
    );
  }
  return false;
}

function nameOf(node, tree) {
  if (!node) return "";
  return ts.isIdentifier(node) ||
    ts.isStringLiteral(node) ||
    ts.isPrivateIdentifier(node)
    ? node.text
    : node.getText(tree);
}

/** "copy", "code" or "prose-test": what the literal's slot says it is. */
function slotOf(subject, tree) {
  let child = subject;
  let node = subject.parent;
  while (node && isTransparent(node, child)) {
    child = node;
    node = node.parent;
  }
  if (!node) return "prose-test";
  if (ts.isJsxAttribute(node)) {
    const name = nameOf(node.name, tree);
    if (CODE_NAMES.has(name) || name.startsWith("data-")) return "code";
    return COPY_NAMES.has(name) ? "copy" : "prose-test";
  }
  if (ts.isJsxElement(node) || ts.isJsxFragment(node)) return "copy";
  if (ts.isPropertyAssignment(node)) {
    if (child === node.name) return "code";
    const name = nameOf(node.name, tree);
    if (CODE_NAMES.has(name)) return "code";
    return COPY_NAMES.has(name) ? "copy" : "prose-test";
  }
  if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
    const callee = ts.isNewExpression(node)
      ? `new ${node.expression.getText(tree)}`
      : node.expression.getText(tree);
    if (callee === "toast" || callee.startsWith("toast.")) return "copy";
    return CODE_CALLEES.test(callee) ? "code" : "prose-test";
  }
  if (
    ts.isImportDeclaration(node) ||
    ts.isExportDeclaration(node) ||
    ts.isExternalModuleReference(node) ||
    ts.isLiteralTypeNode(node) ||
    ts.isImportTypeNode(node) ||
    ts.isElementAccessExpression(node) ||
    ts.isComputedPropertyName(node) ||
    ts.isCaseClause(node) ||
    ts.isEnumMember(node) ||
    ts.isExpressionStatement(node)
  ) {
    return "code";
  }
  return "prose-test";
}

function templateText(template) {
  return [
    template.head.text,
    ...template.templateSpans.map((span) => span.literal.text),
  ].join("{}");
}

export function webStrings(source, path) {
  const tree = ts.createSourceFile(
    path,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const lineAt = (pos) => tree.getLineAndCharacterOfPosition(pos).line + 1;
  const found = [];
  const visit = (node) => {
    if (ts.isJsxText(node)) {
      const text = node.text.trim();
      if (text) {
        const lead = node.text.length - node.text.trimStart().length;
        found.push({ line: lineAt(node.pos + lead), text, audience: "researcher" });
      }
    } else if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const slot = slotOf(node, tree);
      if (slot === "copy" || (slot === "prose-test" && PROSE.test(node.text))) {
        found.push({
          line: lineAt(node.getStart(tree)),
          text: node.text,
          audience: "researcher",
        });
      }
    } else if (ts.isTemplateExpression(node)) {
      const slot = slotOf(node, tree);
      if (
        slot === "copy" ||
        (slot === "prose-test" && PROSE.test(templateText(node)))
      ) {
        const parts = [node.head, ...node.templateSpans.map((span) => span.literal)];
        for (const part of parts) {
          if (part.text) {
            found.push({
              line: lineAt(part.getStart(tree)),
              text: part.text,
              audience: "researcher",
            });
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return found;
}

/** The identifiers of `identifiers` a template or a JSX expression puts in copy. */
export function webRawValues(source, path, identifiers) {
  const tree = ts.createSourceFile(
    path,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const found = [];
  const visit = (node) => {
    const name = ts.isIdentifier(node)
      ? ts.isPropertyAccessExpression(node.parent)
        ? null
        : node.text
      : ts.isPropertyAccessExpression(node)
        ? node.name.text
        : null;
    if (name !== null && identifiers.has(name)) {
      const template = ts.isTemplateSpan(node.parent) ? node.parent.parent : null;
      const slot = slotOf(node, tree);
      const inCopy =
        slot === "copy" ||
        (template !== null &&
          slot === "prose-test" &&
          PROSE.test(templateText(template)));
      if (inCopy) {
        const line = tree.getLineAndCharacterOfPosition(node.getStart(tree)).line + 1;
        found.push({ line, identifier: name });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
  return found;
}

// ---------------------------------------------------------------- python

const STRING_PREFIX = /^(r|u|b|f|t|br|rb|fr|rf|tr|rt)$/i;
const IDENT_START = /[A-Za-z_]/;
const IDENT = /[A-Za-z0-9_]/;
const OPERATORS = [
  "**=",
  "//=",
  ">>=",
  "<<=",
  "...",
  "->",
  ":=",
  "==",
  "!=",
  "<=",
  ">=",
  "+=",
  "-=",
  "*=",
  "/=",
  "%=",
  "&=",
  "|=",
  "^=",
  "@=",
  "**",
  "//",
  "<<",
  ">>",
];
const LOGGER = /^(_?log|_?logger|LOG|LOGGER|_LOG|_LOGGER|logging|warnings)\.\w+$/;
// A trace row shows a tool's summary, so the researcher reads it as well.
const SUMMARY = /(^|\.)with_summary$/;

/** Reads one Python string starting at the quote; returns its text and end. */
function readPythonString(source, start, prefix) {
  const raw = /r/i.test(prefix);
  const formatted = /[ft]/i.test(prefix);
  const quote = source[start];
  const triple = source.startsWith(quote.repeat(3), start);
  const closer = triple ? quote.repeat(3) : quote;
  let i = start + closer.length;
  let text = "";
  while (i < source.length) {
    if (source.startsWith(closer, i)) return { text, end: i + closer.length };
    const ch = source[i];
    if (ch === "\\") {
      const next = source[i + 1] ?? "";
      text += !raw && "ntr".includes(next) && next ? " " : ch + next;
      i += 2;
      continue;
    }
    if (formatted && ch === "{") {
      if (source[i + 1] === "{") {
        text += "{";
        i += 2;
        continue;
      }
      i = skipPythonExpression(source, i + 1);
      text += "{}";
      continue;
    }
    if (formatted && ch === "}" && source[i + 1] === "}") {
      text += "}";
      i += 2;
      continue;
    }
    if (!triple && ch === "\n") return { text, end: i };
    text += ch;
    i += 1;
  }
  return { text, end: i };
}

/** Skips an f-string replacement field; returns the index after its brace. */
function skipPythonExpression(source, start) {
  let depth = 1;
  let i = start;
  while (i < source.length && depth > 0) {
    const ch = source[i];
    if (ch === "'" || ch === '"') {
      let p = i;
      while (p > start && IDENT.test(source[p - 1])) p -= 1;
      const prefix = source.slice(p, i);
      i = readPythonString(source, i, STRING_PREFIX.test(prefix) ? prefix : "").end;
      continue;
    }
    if ("{[(".includes(ch)) depth += 1;
    if ("}])".includes(ch)) depth -= 1;
    i += 1;
  }
  return i;
}

function pythonTokens(source) {
  const tokens = [];
  let line = 1;
  let depth = 0;
  let i = 0;
  const countLines = (from, to) => {
    for (let k = from; k < to; k += 1) if (source[k] === "\n") line += 1;
  };
  while (i < source.length) {
    const ch = source[i];
    if (ch === "#") {
      while (i < source.length && source[i] !== "\n") i += 1;
      continue;
    }
    if (ch === "\\" && source[i + 1] === "\n") {
      i += 2;
      line += 1;
      continue;
    }
    if (ch === "\n") {
      if (depth === 0) tokens.push({ type: "newline", line });
      line += 1;
      i += 1;
      continue;
    }
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }
    if (IDENT_START.test(ch)) {
      let end = i;
      while (end < source.length && IDENT.test(source[end])) end += 1;
      const word = source.slice(i, end);
      if ((source[end] === "'" || source[end] === '"') && STRING_PREFIX.test(word)) {
        const startLine = line;
        const { text, end: after } = readPythonString(source, end, word);
        countLines(i, after);
        tokens.push({ type: "string", text, line: startLine });
        i = after;
        continue;
      }
      tokens.push({ type: "name", value: word, line });
      i = end;
      continue;
    }
    if (ch === "'" || ch === '"') {
      const startLine = line;
      const { text, end } = readPythonString(source, i, "");
      countLines(i, end);
      tokens.push({ type: "string", text, line: startLine });
      i = end;
      continue;
    }
    const op = OPERATORS.find((candidate) => source.startsWith(candidate, i)) ?? ch;
    if ("([{".includes(op)) depth += 1;
    if (")]}".includes(op)) depth = Math.max(0, depth - 1);
    tokens.push({ type: "op", value: op, line });
    i += op.length;
  }
  return tokens;
}

function calleeBefore(tokens, index) {
  const parts = [];
  let k = index - 1;
  while (k >= 0 && tokens[k].type === "name") {
    parts.unshift(tokens[k].value);
    if (k >= 1 && tokens[k - 1].type === "op" && tokens[k - 1].value === ".") k -= 2;
    else break;
  }
  return parts.length > 0 ? parts.join(".") : null;
}

/** The strings of one Python file a reader of the given scope ("model" or "detail") sees. */
export function pythonStrings(source, { scope = "model", toolNames = new Set() } = {}) {
  const tokens = pythonTokens(source);
  const found = [];
  const stack = [];
  let lineStart = true;
  let header = null;
  let docstringOf = null;
  let group = [];

  const flush = () => {
    if (group.length === 0) return;
    const { docstring, kwarg, logged, summary } = group[0];
    const joined = group.map((t) => t.text).join("");
    const keep =
      scope === "detail"
        ? kwarg === "detail" || kwarg === "title"
        : docstring !== null
          ? docstring !== "" && toolNames.has(docstring)
          : !logged && PROSE.test(joined);
    const audience = scope === "detail" ? "researcher" : summary ? "both" : "model";
    if (keep)
      for (const t of group) found.push({ line: t.line, text: t.text, audience });
    group = [];
  };

  const activeKwarg = () => {
    for (let k = stack.length - 1; k >= 0; k -= 1) {
      if (stack[k].kwarg) return stack[k].kwarg;
      if (stack[k].callee !== null || stack[k].char !== "(") return null;
    }
    return null;
  };

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token.type !== "string") flush();
    if (token.type === "newline") {
      const last = tokens[index - 1];
      docstringOf =
        header !== null && last?.type === "op" && last.value === ":" ? header : null;
      header = null;
      lineStart = true;
      continue;
    }
    const first = lineStart;
    lineStart = false;
    if (token.type === "string") {
      const isDocstring =
        first && group.length === 0 && (docstringOf !== null || index === 0);
      group.push({
        ...token,
        docstring: isDocstring ? (docstringOf ?? "") : null,
        kwarg: activeKwarg(),
        logged: stack.some(
          (entry) => entry.callee !== null && LOGGER.test(entry.callee),
        ),
        summary: SUMMARY.test(
          stack.findLast((entry) => entry.callee !== null)?.callee ?? "",
        ),
      });
      docstringOf = null;
      continue;
    }
    docstringOf = null;
    if (token.type === "name") {
      if (first && token.value === "async") lineStart = true;
      if (
        (first || tokens[index - 1]?.value === "async") &&
        ["def", "class"].includes(token.value)
      ) {
        header = tokens[index + 1]?.value ?? "";
      }
      const next = tokens[index + 1];
      if (stack.length > 0 && next?.type === "op" && next.value === "=") {
        stack[stack.length - 1].kwarg = token.value;
      }
      continue;
    }
    if ("([{".includes(token.value)) {
      const callee = token.value === "(" ? calleeBefore(tokens, index) : null;
      stack.push({ char: token.value, callee, kwarg: null });
    } else if (")]}".includes(token.value)) {
      stack.pop();
    } else if (token.value === "," && stack.length > 0) {
      stack[stack.length - 1].kwarg = null;
    }
  }
  flush();
  return found;
}

/** The names a `Tool(...)` or a `FunctionToolset(tools=[...])` registers. */
export function toolNamesIn(source) {
  const names = new Set();
  for (const match of source.matchAll(/\bTool\(\s*([A-Za-z_]\w*)/g))
    names.add(match[1]);
  for (const match of source.matchAll(/\btools\s*=\s*\[/g)) {
    let depth = 1;
    let i = match.index + match[0].length;
    let item = "";
    const items = [];
    while (i < source.length && depth > 0) {
      const ch = source[i];
      if ("([{".includes(ch)) depth += 1;
      if (")]}".includes(ch)) depth -= 1;
      if ((ch === "," && depth === 1) || depth === 0) {
        items.push(item);
        item = "";
      } else {
        item += ch;
      }
      i += 1;
    }
    for (const one of items) {
      const bare = one.replace(/#.*$/gm, "").trim();
      if (/^[A-Za-z_]\w*$/.test(bare)) names.add(bare);
    }
  }
  return names;
}

// -------------------------------------------------------------- findings

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function patternFor(synonym) {
  const phrase = synonym.split(/\s+/).map(escapeRegExp).join("\\s+");
  return new RegExp(`(?<![A-Za-z0-9_-])${phrase}(?:e?s)?(?![A-Za-z0-9_-])`, "gi");
}

const exempted = (exemptions, synonym, path) =>
  exemptions.some(
    (e) =>
      e.synonym.toLowerCase() === synonym.toLowerCase() &&
      (e.path === path || (e.path.endsWith("/") && path.startsWith(e.path))),
  );

export function findingsIn(strings, rows, path, exemptions) {
  const findings = [];
  for (const { line, text, audience } of strings) {
    const hits = [];
    for (const { name, banned, scope } of rows) {
      if (scope === "researcher" && audience === "model") continue;
      for (const synonym of banned) {
        if (exempted(exemptions, synonym, path)) continue;
        for (const match of text.matchAll(patternFor(synonym))) {
          const offset = text.slice(0, match.index).split("\n").length - 1;
          hits.push({
            index: match.index,
            finding: { path, line: line + offset, synonym, name },
          });
        }
      }
    }
    hits.sort((a, b) => a.index - b.index);
    findings.push(...hits.map((hit) => hit.finding));
  }
  return findings;
}

// ------------------------------------------------------------------ main

function filesUnder(dir, extensions) {
  return readdirSync(dir).flatMap((name) => {
    if (SKIPPED.has(name)) return [];
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return filesUnder(full, extensions);
    const rel = relative(ROOT, full);
    return extensions.some((ext) => name.endsWith(ext)) && !TEST_FILE.test(rel)
      ? [rel]
      : [];
  });
}

function collect() {
  const { rows, exemptions, rawValues } = parseLexicon(
    readFileSync(join(ROOT, LEXICON), "utf8"),
  );
  const rawNames = new Map(rawValues.map((raw) => [raw.identifier, raw.name]));
  const read = (path) => readFileSync(join(ROOT, path), "utf8");
  const findings = [];
  const add = (path, strings) =>
    findings.push(...findingsIn(strings, rows, path, exemptions));

  for (const path of WEB_TREES.flatMap((tree) =>
    filesUnder(join(ROOT, tree), [".ts", ".tsx"]),
  )) {
    add(path, webStrings(read(path), path));
    for (const { line, identifier } of webRawValues(
      read(path),
      path,
      new Set(rawNames.keys()),
    )) {
      findings.push({
        path,
        line,
        synonym: identifier,
        name: rawNames.get(identifier),
      });
    }
  }
  const modelFiles = MODEL_TREES.flatMap((tree) =>
    filesUnder(join(ROOT, tree), [".py"]),
  );
  const toolNames = new Set(modelFiles.flatMap((path) => [...toolNamesIn(read(path))]));
  for (const path of modelFiles) add(path, pythonStrings(read(path), { toolNames }));
  for (const path of MODEL_TREES.flatMap((tree) =>
    filesUnder(join(ROOT, tree), [".md"]),
  )) {
    const lines = read(path).split("\n");
    add(
      path,
      lines.map((text, index) => ({ line: index + 1, text, audience: "model" })),
    );
  }
  for (const path of DETAIL_TREES.flatMap((tree) =>
    filesUnder(join(ROOT, tree), [".py"]),
  )) {
    add(path, pythonStrings(read(path), { scope: "detail" }));
  }
  return findings;
}

function main() {
  const findings = collect();
  if (findings.length === 0) {
    console.log("check-vocabulary: every concept is called by its one name.");
    return;
  }
  for (const { path, line, synonym, name } of findings) {
    console.error(`${path}:${line}: "${synonym}" -> "${name}"`);
  }
  const bySynonym = new Map();
  for (const { synonym } of findings)
    bySynonym.set(synonym, (bySynonym.get(synonym) ?? 0) + 1);
  console.error("");
  for (const [synonym, count] of bySynonym) console.error(`  ${synonym}: ${count}`);
  console.error(
    `\ncheck-vocabulary: ${findings.length} banned synonym(s) or raw value(s) in text a researcher or the model reads.`,
  );
  console.error(
    `Use the name ${LEXICON} gives the concept or the value, or add an exemption with its reason.`,
  );
  process.exit(1);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main();
