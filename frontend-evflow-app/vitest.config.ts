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
      // Collect over the whole source tree, not a hand-kept whitelist.
      //
      // The whitelist named six files out of 138, and SonarQube treats a file it
      // analyses but has no coverage data for as 0% covered. So every module
      // outside the list reported zero even where tests existed and passed:
      // apiStationStatus.ts measures 95% locally and was scored 0. That is what
      // failed the new-code coverage gate, not a real lack of tests.
      // .ts only, matching sonar.coverage.exclusions which already drops **/*.tsx
      // and packages/ui. Collecting screens here would only make the local number
      // disagree with the one the gate actually reads.
      include: ['packages/*/src/**/*.ts'],
      exclude: [
        '**/*.test.ts',
        '**/*.d.ts',
        // Mirrors sonar.coverage.exclusions: the UI and map packages are
        // presentation, tested through the pure logic modules they consume.
        'packages/ui/**',
        'packages/maps/**',
        // Re-export barrels: no behaviour of their own to cover.
        '**/index.ts',
        // Static artwork and design tokens. These are data written as modules;
        // a test would assert the constant against itself.
        '**/*Icons.ts',
        '**/*Icons.native.ts',
        '**/routeTheme.ts',
        '**/styles/**'
      ]
    }
  }
});
