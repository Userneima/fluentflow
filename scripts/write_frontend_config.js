const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "frontend", "assets");
const outFile = path.join(outDir, "config.js");

const normalizeApiBase = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  return raw.replace(/\/+$/, "");
};

const config = {
  apiBase: normalizeApiBase(process.env.FLUENTFLOW_API_BASE),
};

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(
  outFile,
  `window.FLUENTFLOW_CONFIG = ${JSON.stringify(config, null, 2)};\n`,
  "utf8"
);
