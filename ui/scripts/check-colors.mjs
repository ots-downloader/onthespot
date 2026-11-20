// Fails when a colour is written outside the theme tokens in src/index.css.
// Colours must come from role utilities (bg-surface, text-fg, border-line...).
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src", import.meta.url));

// Brand colours of the music services are data, not theme.
const exempt = new Set(["index.css", ["lib", "catalogServices.ts"].join(sep)]);

const hues =
  "neutral|stone|zinc|gray|slate|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";
const prefixes =
  "bg|text|border|ring|ring-offset|outline|divide|from|via|to|fill|stroke|decoration|accent|caret|shadow|placeholder";

const rules = [
  ["dark: variant", /\bdark:/],
  ["raw palette class", new RegExp(String.raw`\b(?:${prefixes})(?:-[trblxyse])?-(?:${hues})-\d{2,3}\b`)],
  ["hex colour", /#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b/],
  ["colour function", /\b(?:rgba?|hsla?|oklch)\(/],
];

function* walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else if (/\.(tsx?|css)$/.test(entry.name)) yield path;
  }
}

const problems = [];
for (const file of walk(root)) {
  const name = relative(root, file);
  if (exempt.has(name)) continue;
  readFileSync(file, "utf8")
    .split(/\r?\n/)
    .forEach((line, index) => {
      // Comments cite issues ("#448") and links point at anchors ("#top").
      const code = line.replace(/(?:^|\s)\/\/.*$|^\s*\/?\*.*$/, "").replace(/href="#[^"]*"/g, "");
      for (const [label, pattern] of rules) {
        const match = code.match(pattern);
        if (match) problems.push(`src/${name.split(sep).join("/")}:${index + 1}  ${label}: ${match[0]}`);
      }
    });
}

if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(
    `\n${problems.length} colour(s) written outside the theme. Use a role utility from src/index.css.`,
  );
  process.exit(1);
}
