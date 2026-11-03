// Copies the version Changesets wrote to package.json into .claude-plugin/plugin.json.
// `--check` only compares them and exits 1 when they differ (for CI).
import { readFileSync, writeFileSync } from "node:fs";

const read = (path) => JSON.parse(readFileSync(path, "utf8"));
const pkg = read("package.json");
const pluginPath = ".claude-plugin/plugin.json";
const plugin = read(pluginPath);

if (process.argv.includes("--check")) {
  if (plugin.version !== pkg.version) {
    console.error(`plugin.json is ${plugin.version} but package.json is ${pkg.version}; run npm run version`);
    process.exit(1);
  }
  console.log(`plugin.json and package.json are both ${pkg.version}`);
} else {
  plugin.version = pkg.version;
  writeFileSync(pluginPath, `${JSON.stringify(plugin, null, 2)}\n`);
  console.log(`plugin.json -> ${pkg.version}`);
}
