# Mutation testing tools

Use when filling the Mutation testing part of the project contract (`project-onboarding` skill), or when running a tool on a lot. One section per tool: the tool id used by `onboard.py --mutation-tool`, how to run it on the changed files, the report the gate script reads, how to disable an equivalent mutant in the code, and the folders to keep out of git. Every section ends with its sources; what the sources do not state is marked **To confirm**. Commands marked "checked" were run on a sample project on 2026-11-26.

The gate script (`scripts/mutation_gate.py`) reads two report formats:

- `mutation-testing-elements`: the JSON report schema shared by the Stryker tools ([schema](https://github.com/stryker-mutator/mutation-testing-elements/tree/master/packages/report-schema), [metrics](https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/)). It carries the source of each file, so the script also refuses a report older than the code.
- `pitest-xml`: the `mutations.xml` report of PIT (`outputFormats` XML).

For the other tools the contract says `tool`: use the tool's own changed-code mode and threshold, and compute the score of the changed lines from its output.

## Stryker.NET (`stryker-net`) — .NET (C#)

- **Install:** as a local tool, `dotnet new tool-manifest` then `dotnet tool install dotnet-stryker`; teammates run `dotnet tool restore`. Running Stryker.NET needs the .NET 10 runtime or later; the project may target an earlier .NET.
- **Run on the changed files:** from the test project folder (from the project under test when several test projects cover it): `dotnet stryker --reporter json --reporter html --mutate "**/Pricing.cs" --mutate "**/Rates.cs"`. For a whole branch, `--since:<base_sha>` reports only the mutants within the code changed since that commit. Configuration file: `stryker-config.json`. `--mutation-level` is `Standard` by default.
- **Report for the gate:** the `json` reporter writes `mutation-report.json` (`report-file-name`) in the run's output folder (`--output <folder>` sets it). **To confirm** on the first run: the folder (`StrykerOutput/<date-time>/reports/`) and the mutation-testing-elements format of the JSON report are not stated by the documentation; the gate script says "not a mutation-testing-elements report" otherwise.
- **Tool thresholds:** `--threshold-high` (80), `--threshold-low` (60), `--break-at` (0, disabled) apply to the whole run; the workflow's gate is the score of the changed lines.
- **Disable a mutant in the code:** `// Stryker disable once <Mutator>: <reason>` on the line before (`// Stryker disable all: <reason>` ... `// Stryker restore all` for a block); `ignore-methods` for calls such as logging.
- **Keep out of git:** `StrykerOutput/`.
- **Notes:** C# only (F# and VB are not mentioned by the documentation). Stryker.NET uses mutant schemata.
- **Sources:** https://stryker-mutator.io/docs/stryker-net/getting-started/ · https://stryker-mutator.io/docs/stryker-net/configuration/ · https://stryker-mutator.io/docs/stryker-net/reporters/ · https://stryker-mutator.io/docs/stryker-net/ignore-mutations/ · https://stryker-mutator.io/docs/stryker-net/technical-reference/mutant-schemata/

## StrykerJS (`stryker-js`) — JavaScript and TypeScript

- **Install:** `npm init stryker@latest` installs Stryker and runs its initializer, which writes `stryker.config.mjs` and sets up the test runner (`jest`, `vitest`, `mocha`, `karma`, `jasmine`, `cucumber`, `tap`, or `command` to run any test command).
- **Run on the changed files:** `npx stryker run --reporters json,html,clear-text --mutate "src/pricing.ts,src/rates.ts"` (checked with StrykerJS 10.1). `--mutate src/app.js:5-7` restricts a file to a line range. `--incremental` reuses the results of unchanged code from `reports/stryker-incremental.json`.
- **Report for the gate:** `reports/mutation/mutation.json` (`jsonReporter.fileName`), mutation-testing-elements format (checked).
- **Tool thresholds:** `thresholds: { high: 80, low: 60, break: null }`; below `break`, Stryker exits with code 1.
- **Disable a mutant in the code:** `// Stryker disable next-line <Mutator>: <reason>` (`// Stryker disable all: <reason>` ... `// Stryker restore all` for a block). Disabled mutants get the `Ignored` status: out of the score, reason shown in the report.
- **Keep out of git:** `.stryker-tmp/` (the sandbox, deleted after a successful run but left after a failed one, checked), `reports/mutation/`, `reports/stryker-incremental.json`.
- **Notes:** Stryker works on a copy in the sandbox; keep `inPlace` at its default (`false`).
- **Sources:** https://stryker-mutator.io/docs/stryker-js/getting-started/ · https://stryker-mutator.io/docs/stryker-js/configuration/ · https://stryker-mutator.io/docs/stryker-js/incremental/ · https://stryker-mutator.io/docs/stryker-js/disable-mutants/

## PIT (`pitest`) — JVM (Java)

- **Install:** Maven plugin `org.pitest:pitest-maven`, with the `org.pitest:pitest-junit5-plugin` dependency for JUnit 5; Gradle plugin `info.solidsoft.pitest` (`junit5PluginVersion`).
- **Run on the changed classes:** `mvn test-compile org.pitest:pitest-maven:mutationCoverage -DtargetClasses=com.example.Pricing,com.example.Rates -DoutputFormats=XML,HTML -DtimestampedReports=false` (checked with pitest-maven 1.20.0 and pitest-junit5-plugin 1.2.3). Gradle: `gradle pitest` with `targetClasses`, `outputFormats = ['XML', 'HTML']` and `timestampedReports = false` in the `pitest { }` block. `-DwithHistory` reuses the results of unchanged code. The open-source `scmMutationCoverage` goal is no longer supported; PIT's git integration is in the commercial Arcmutate.
- **Report for the gate:** `target/pit-reports/mutations.xml` (Maven, checked) or `build/reports/pitest/mutations.xml` (Gradle), `pitest-xml` format.
- **Tool thresholds:** `mutationThreshold` fails the build below it (whole run).
- **Disable a mutant in the code:** no inline comment in the open-source PIT. Use `excludedMethods`, `excludedClasses` or `avoidCallsTo` (logging packages by default) in the plugin configuration, with an XML comment giving the reason.
- **Keep out of git:** `target/pit-reports/`, `build/reports/pitest/`.
- **Notes:** PIT mutates bytecode. Kotlin projects: **To confirm** (not covered by the pages below).
- **Sources:** https://pitest.org/quickstart/maven · https://gradle-pitest-plugin.solidsoft.info/ · https://groups.google.com/g/pitusers/c/PJ8kqod_8Q8

## mutmut (`mutmut`) — Python

- **Install:** `pip install mutmut` as a development dependency; it runs the tests with pytest. It needs `fork`: on Windows, run it inside WSL. Configuration in `pyproject.toml`: `[tool.mutmut]` with `source_paths = ["src/"]` (checked with mutmut 3.8.1).
- **Run on the changed modules:** `mutmut run "<module>*"`, for example `mutmut run "shop.pricing*"` (checked). `mutmut results` lists the surviving mutants, `mutmut show <mutant>` prints the diff of one (file and line), `mutmut export-cicd-stats` writes the counts to `mutants/mutmut-cicd-stats.json` (checked).
- **Report for the gate:** `tool`. mutmut mutates whole functions and has no changed-lines report: list the survivors of the changed functions with `mutmut show`, keep those on changed lines, and compute the score from them.
- **Tool thresholds:** none.
- **Disable a mutant in the code:** `# pragma: no mutate` at the end of the line (`# pragma: no mutate block`, or `# pragma: no mutate start` ... `# pragma: no mutate end`), with the reason in a comment next to it.
- **Keep out of git:** `mutants/`.
- **Notes:** mutmut copies the code into `mutants/` and leaves the sources alone, except `mutmut apply`, which writes a mutant into the source: never use it in the workflow. On Windows without WSL, Cosmic Ray (`cosmic-ray`) is an alternative; it makes its mutations directly on disk, so check `git diff` after each run.
- **Sources:** https://raw.githubusercontent.com/boxed/mutmut/master/README.rst · https://mutmut.readthedocs.io · https://cosmic-ray.readthedocs.io/en/latest/tutorials/intro/index.html

## Infection (`infection`) — PHP

- **Install:** `infection.phar` from the GitHub releases, `phive install infection`, or `composer global require infection/infection`. Configuration: `infection.json5`.
- **Run on the changed lines:** `infection --git-diff-lines --git-diff-base=<base_sha> --min-msi=<threshold> --threads=4`. `--git-diff-lines` limits the mutants to the added and modified lines, so Infection computes the score of the changed lines itself (MSI). **To confirm:** whether uncommitted changes are included before the lot's commit.
- **Report for the gate:** `tool`. MSI in the output; `--min-msi` makes Infection fail below the threshold; `--logger-json <file>` writes Infection's own JSON (not the mutation-testing-elements schema).
- **Disable a mutant in the code:** `// @infection-ignore-all`, or `// @infection-ignore <Mutator>`, with the reason in a comment line above it. Such mutants are not generated at all.
- **Keep out of git:** the log files set in the `logs` of `infection.json5`.
- **Sources:** https://infection.github.io/guide/command-line-options.html · https://infection.github.io/guide/usage.html · https://infection.github.io/guide/how-to.html · https://infection.github.io/guide/installation.html

## cargo-mutants (`cargo-mutants`) — Rust

- **Install:** `cargo install --locked cargo-mutants`.
- **Run on the changed lines:** write the diff outside the repository, then `cargo mutants --in-diff <file>`: only the mutants that overlap the changed regions are tested. For a lot: `git diff HEAD > <temp folder>/lot.diff`; for a review: `git diff <base_sha>..HEAD`.
- **Report for the gate:** `tool`. Exit code 0 when every viable mutant is caught, 2 when some are missed, 3 on timeouts; the lists are in `mutants.out/` (`caught.txt`, `missed.txt`, `timeout.txt`, `outcomes.json`).
- **Disable a mutant in the code:** `#[mutants::skip]` on the item (needs the `mutants` crate), or `exclude_re` in `.cargo/mutants.toml`, with a comment giving the reason.
- **Keep out of git:** `mutants.out/`, `mutants.out.old/`.
- **Notes:** cargo-mutants builds and tests a copy of the source in a scratch directory.
- **Sources:** https://mutants.rs/in-diff.html · https://mutants.rs/mutants-out.html · https://mutants.rs/exit-codes.html · https://mutants.rs/skip.html · https://mutants.rs/attrs.html · https://mutants.rs/installation.html

## Other stacks

- Scala: Stryker4s writes the mutation-testing-elements report too (https://stryker-mutator.io/docs/stryker4s/configuration/); not detected by onboarding.
- Go and other stacks: no tool checked yet. Choose one with the user, record it in the contract with the `tool` report format, and add a section here.
