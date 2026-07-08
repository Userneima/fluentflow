import { defineConfig } from 'vitest/config';

// Scoped to pure logic modules under frontend/src/lib. These have no DOM or
// browser dependency, so the node environment is enough and no React/JSX
// transform is loaded. See docs/task_list_reconciliation_plan.md.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['frontend/src/lib/**/*.test.js'],
  },
});
