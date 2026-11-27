import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [packageDirectory, scriptPath, targetDirectory] = process.argv.slice(2);
const { default: espeak } = await import(pathToFileURL(join(packageDirectory, "dist/espeak-ng.js")).href);
const wasmBinary = readFileSync(join(packageDirectory, "dist/espeak-ng.wasm"));
const lines = JSON.parse(readFileSync(scriptPath, "utf8"));
for (const [index, line] of lines.entries()) {
  const result = await espeak({
    wasmBinary,
    arguments: ["-v", "cmn", "-s", "155", "-w", "speech.wav", line],
  });
  writeFileSync(join(targetDirectory, "speech-" + index + ".wav"), result.FS.readFile("speech.wav"));
}
