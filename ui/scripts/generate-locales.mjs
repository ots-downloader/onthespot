import { mkdir, readFile, writeFile } from "node:fs/promises";
import { glob } from "node:fs/promises";
import ts from "typescript";

const args = process.argv.slice(2);
const mode = args[0]?.startsWith("--") ? args.shift() : "--generate";
const locales = args.length
  ? args
  : ["de", "es", "fr", "it", "ja", "ko", "nl", "pl", "pt", "tr", "uk", "zh-CN", "zh-TW"];
const split = "[[OTS_TRANSLATION_SPLIT]]";
const files = [];
for await (const file of glob("src/**/*.{ts,tsx}", { cwd: process.cwd() })) files.push(file);

const excludedSources = new Set([
  "src/lib/i18n.ts",
  "src/lib/localizeDocument.ts",
  "src/types.ts",
]);
const cssToken = /^(?:(?:sm|md|lg|xl|2xl|dark|hover|focus|active|disabled|group-hover):)*(?:ots-[\w-[\]]+|(?:-?m[trblxy]?|-?p[trblxy]?|w|h|min-[wh]|max-[wh]|gap[xy]?|space-[xy]|grid-cols|grid-rows|col-span|row-span|z|inset|top|right|bottom|left|translate-[xy]|scale|opacity|duration|delay|order|basis|grow|shrink|rounded|border|bg|text|font|leading|tracking|shadow|ring|divide-[xy]|object|overflow-[xy]|line-clamp)-[^\s]+|grid|flex|inline-flex|block|inline|hidden|relative|absolute|fixed|sticky|items-[\w-]+|justify-[\w-]+|self-[\w-]+|content-[\w-]+|cursor-[\w-]+|select-[\w-]+|truncate|antialiased|appearance-none|transition(?:-[\w-]+)?|transform|animate-[^\s]+|pointer-events-[\w-]+|whitespace-[\w-]+)$/;

const isTechnicalValue = (value) => {
  if (/^(?:\.\.?\/|\/|\?|#|[A-Za-z]:\\)/.test(value)) return true;
  if (/\\|\r|\n|\.(?:tsx?|jsx?|css|json|mjs)$|^\[data-|\.replace\(\/|^application\//.test(value)) return true;
  if (/^(?:GET|POST|PUT|PATCH|DELETE|Content-Type|react-dom\/client)$/.test(value)) return true;
  const tokens = value.split(/\s+/).filter(Boolean);
  if (tokens.some((token) => token.startsWith("ots-"))) return true;
  return tokens.length > 1 && tokens.filter((token) => cssToken.test(token)).length / tokens.length >= 0.5;
};

const candidates = new Set();
const addCandidate = (rawValue) => {
  const value = rawValue.replace(/\s+/g, " ").trim();
  if (value.length < 2 || value.length > 180 || !/[A-Za-z]/.test(value)) return;
  if (/^(https?:|\/|#|[\w.-]+$|[\w-]+(?:\s+[\w-]+){0,2}$)/.test(value) && !/[A-Z]/.test(value)) return;
  if (/[{}]|=>|className|text-|bg-|border-|\bflex\b|\bpx-\d|\bpy-\d/.test(value)) return;
  if (isTechnicalValue(value)) return;
  candidates.add(value);
};

for (const file of files) {
  if (excludedSources.has(file.replaceAll("\\", "/"))) continue;
  const source = await readFile(file, "utf8");
  for (const match of source.matchAll(/(['"])((?:\\.|(?!\1).)*)\1/g)) {
    addCandidate(match[2].replace(/\\(['"\\])/g, "$1"));
  }

  if (file.endsWith(".tsx")) {
    const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node) => {
      if (ts.isJsxText(node)) addCandidate(node.getText(sourceFile));
      ts.forEachChild(node, visit);
    };
    visit(sourceFile);
  }
}

const phrases = [...candidates].sort((a, b) => a.localeCompare(b));
const buildBatches = (sourcePhrases) => {
  const batches = [];
  let batch = [];
  let length = 0;
  for (const phrase of sourcePhrases) {
    const nextLength = length + phrase.length + split.length + 2;
    if (batch.length && nextLength > 4000) {
      batches.push(batch);
      batch = [];
      length = 0;
    }
    batch.push(phrase);
    length += phrase.length + split.length + 2;
  }
  if (batch.length) batches.push(batch);
  return batches;
};

await mkdir("src/locales", { recursive: true });

if (mode === "--verify" || mode === "--prune") {
  let invalid = false;
  for (const locale of locales) {
    const path = `src/locales/${locale}.json`;
    const existing = JSON.parse(await readFile(path, "utf8"));
    const missing = phrases.filter((phrase) => !(phrase in existing));
    const extras = Object.keys(existing).filter((phrase) => !candidates.has(phrase));
    if (mode === "--prune") {
      const dictionary = Object.fromEntries(phrases.map((phrase) => [phrase, existing[phrase] || phrase]));
      await writeFile(path, `${JSON.stringify(dictionary, null, 2)}\n`);
      console.log(`Pruned ${locale}: ${Object.keys(existing).length} -> ${phrases.length} phrases`);
    } else if (missing.length || extras.length) {
      invalid = true;
      console.error(`${locale}: ${missing.length} missing, ${extras.length} unexpected phrases`);
      if (missing.length) console.error(`  Missing: ${missing.join(" | ")}`);
      if (extras.length) console.error(`  Unexpected: ${extras.join(" | ")}`);
    } else {
      console.log(`Verified ${locale}: ${phrases.length} phrases`);
    }
  }
  if (invalid) process.exitCode = 1;
} else if (mode === "--generate") {
for (const locale of locales) {
  let existing = {};
  try {
    existing = JSON.parse(await readFile(`src/locales/${locale}.json`, "utf8"));
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  const missing = phrases.filter((phrase) => !(phrase in existing));
  const dictionary = Object.fromEntries(phrases.map((phrase) => [phrase, existing[phrase] || phrase]));
  for (const phrasesInBatch of buildBatches(missing)) {
    const source = phrasesInBatch.join(`\n${split}\n`);
    const response = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=${locale}&dt=t&q=${encodeURIComponent(source)}`);
    if (!response.ok) throw new Error(`Translation request failed for ${locale}: ${response.status}`);
    const body = await response.json();
    const translated = body?.[0]?.map((part) => part?.[0] || "").join("") || "";
    const escapedSplit = split.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const values = translated.split(new RegExp(`\\s*${escapedSplit}\\s*`));
    phrasesInBatch.forEach((phrase, index) => { dictionary[phrase] = values[index] || phrase; });
  }
  await writeFile(`src/locales/${locale}.json`, `${JSON.stringify(dictionary, null, 2)}\n`);
  console.log(`Generated ${locale}: ${Object.keys(dictionary).length} phrases (${missing.length} added)`);
}
} else {
  throw new Error(`Unknown mode: ${mode}`);
}
