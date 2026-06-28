// Lint frontend source via project-level ESLint flat config.
import { execSync } from 'node:child_process';

try {
    execSync(`npx eslint frontend/src/`, { stdio: 'inherit', env: { ...process.env } });
} catch {
    // Warnings exit 1 too
}
