import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // The files under test are pure TypeScript logic with no DOM/React Native
    // dependency, so the lightweight node environment is sufficient.
    environment: 'node',
    include: ['**/*.{test,spec}.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      reportsDirectory: './coverage',
      // Focus the report on the pure logic under test so the generated lcov
      // only carries the files whose new-code coverage the quality gate needs.
      include: [
        'packages/shared/src/validation.ts',
        'packages/shared/src/api/baseUrl.shared.ts'
      ]
    }
  }
});
