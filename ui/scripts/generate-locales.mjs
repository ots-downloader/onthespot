import { mkdir, readFile, writeFile } from "node:fs/promises";
import { glob } from "node:fs/promises";

const locales = process.argv.slice(2).length
  ? process.argv.slice(2)
  : ["de", "es", "fr", "it", "ja", "ko", "nl", "pl", "pt", "tr", "uk", "zh-CN", "zh-TW"];
const split = "[[OTS_TRANSLATION_SPLIT]]";
const files = [];
for await (const file of glob("src/**/*.{ts,tsx}", { cwd: process.cwd() })) files.push(file);

const candidates = new Set();
for (const file of files) {
  const source = await readFile(file, "utf8");
  for (const match of source.matchAll(/(['"])((?:\\.|(?!\1).)*)\1/g)) {
    const value = match[2].replace(/\\(['"\\])/g, "$1").trim();
    if (value.length < 2 || value.length > 180 || !/[A-Za-z]/.test(value)) continue;
    if (/^(https?:|\/|#|[\w.-]+$|[\w-]+(?:\s+[\w-]+){0,2}$)/.test(value) && !/[A-Z]/.test(value)) continue;
    if (/[{}]|=>|className|text-|bg-|border-|\bflex\b|\bpx-\d|\bpy-\d/.test(value)) continue;
    candidates.add(value);
  }
}

const phrases = [...candidates].sort((a, b) => a.localeCompare(b));
const batches = [];
let batch = [];
let length = 0;
for (const phrase of phrases) {
  const nextLength = length + phrase.length + split.length + 2;
  if (batch.length && nextLength > 4000) { batches.push(batch); batch = []; length = 0; }
  batch.push(phrase); length += phrase.length + split.length + 2;
}
if (batch.length) batches.push(batch);

await mkdir("src/locales", { recursive: true });
for (const locale of locales) {
  const dictionary = {};
  for (const phrasesInBatch of batches) {
    const source = phrasesInBatch.join(`\n${split}\n`);
    const response = await fetch(`https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=${locale}&dt=t&q=${encodeURIComponent(source)}`);
    if (!response.ok) throw new Error(`Translation request failed for ${locale}: ${response.status}`);
    const body = await response.json();
    const translated = body?.[0]?.map((part) => part?.[0] || "").join("") || "";
    const values = translated.split(new RegExp(`\\s*${split}\\s*`));
    phrasesInBatch.forEach((phrase, index) => { dictionary[phrase] = values[index] || phrase; });
  }
  await writeFile(`src/locales/${locale}.json`, `${JSON.stringify(dictionary, null, 2)}\n`);
  console.log(`Generated ${locale}: ${Object.keys(dictionary).length} phrases`);
}
