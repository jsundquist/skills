// Prints the CHANGELOG.md section for one version: the text between its "## X.Y.Z" heading and the next one.
// Used by the release workflow for the GitHub release notes.
import { readFileSync } from "node:fs";

const version = process.argv[2];
if (!version) {
  console.error("usage: node scripts/release-notes.mjs X.Y.Z");
  process.exit(2);
}

const lines = readFileSync("CHANGELOG.md", "utf8").split("\n");
const start = lines.findIndex((line) => line.trim() === `## ${version}`);
if (start === -1) {
  console.error(`CHANGELOG.md has no "## ${version}" section; run pnpm run version first`);
  process.exit(1);
}

const next = lines.findIndex((line, i) => i > start && line.startsWith("## "));
const body = lines.slice(start + 1, next === -1 ? lines.length : next).join("\n").trim();
if (!body) {
  console.error(`The "## ${version}" section of CHANGELOG.md is empty`);
  process.exit(1);
}
console.log(body);
