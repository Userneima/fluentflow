const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const frontendDir = path.join(root, "frontend");
const distDir = path.join(root, "dist");

const copyDir = (source, target) => {
  fs.mkdirSync(target, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const sourcePath = path.join(source, entry.name);
    const targetPath = path.join(target, entry.name);
    if (entry.isDirectory()) {
      copyDir(sourcePath, targetPath);
    } else if (entry.isFile()) {
      fs.copyFileSync(sourcePath, targetPath);
    }
  }
};

fs.rmSync(distDir, { recursive: true, force: true });
fs.mkdirSync(distDir, { recursive: true });
fs.copyFileSync(path.join(frontendDir, "index.html"), path.join(distDir, "index.html"));
copyDir(path.join(frontendDir, "assets"), path.join(distDir, "assets"));
