/* Replay Chromium's pinned WebUI lint rules on optional Windows source files.
 * The partial fixture lacks generated Mojo and the transitive WebUI graph.
 * Rules requiring that graph are reported separately, never called verified.
 */
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

async function checkLint({source, rulesDir, modules, program, files, typed = false,
  expectedRules = []}) {
  const ts = require(path.join(modules, 'typescript'));
  const {ESLint} = require(path.join(modules, 'eslint'));
  for (const [name, version] of Object.entries({eslint:'10.2.0',
    '@typescript-eslint/eslint-plugin':'8.58.2', '@typescript-eslint/parser':'8.58.2',
    'eslint-plugin-lit':'2.2.1', typescript:'6.0.2'})) {
    assert.equal(JSON.parse(fs.readFileSync(path.join(modules, name, 'package.json'), 'utf8')).version, version);
  }
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'arcium-webui-lint-'));
  try {
    fs.writeFileSync(path.join(temporary, 'package.json'), '{"type":"module"}');
    const hashes = {};
    for (const file of fs.readdirSync(rulesDir).filter(file => file.endsWith('.ts')).sort()) {
      const original = fs.readFileSync(path.join(rulesDir, file), 'utf8');
      hashes[file] = crypto.createHash('sha256').update(original).digest('hex');
      // Only tool module locations change. Preserve every upstream rule body.
      const text = original.replaceAll('/third_party/node/node_modules/', pathToFileURL(modules + path.sep).href);
      fs.writeFileSync(path.join(temporary, file.replace(/\.ts$/, '.js')),
        ts.transpileModule(text, {compilerOptions:{module:ts.ModuleKind.ESNext,
          target:ts.ScriptTarget.ES2022}}).outputText);
    }
    const {defaultConfig, webComponentMissingDepsConfig, noExplicitAnyConfig} =
      await import(pathToFileURL(path.join(temporary, 'eslint_ts.config_base.js')).href);
    const skipped = typed ? [] : [
      '@webui-eslint/lit-element-expressions', '@webui-eslint/lit-reactive-properties',
      '@webui-eslint/lit-property-accessor', '@webui-eslint/web-component-missing-deps',
      '@typescript-eslint/no-unnecessary-type-assertion', '@typescript-eslint/no-unnecessary-type-conversion',
    ];
    // Match the two optional lint flags in the user's native Settings action.
    const extraConfigs = typed ? [webComponentMissingDepsConfig, noExplicitAnyConfig] : [];
    const linter = new ESLint({cwd:source, overrideConfigFile:true, overrideConfig:[...defaultConfig, ...extraConfigs,
      {languageOptions:{parserOptions:{programs:[program]}},
        rules:Object.fromEntries(skipped.map(rule => [rule, 'off']))}]});
    const results = await linter.lintFiles(files);
    const diagnostics = results.flatMap(result => result.messages.map(message =>
      `${path.relative(source, result.filePath)}:${message.line}:${message.column} ${message.ruleId}: ${message.message}`));
    assert.deepEqual(results.flatMap(result => result.messages.map(message => message.ruleId)).sort(),
      [...expectedRules].sort(), diagnostics.join('\n'));
    return {status:expectedRules.length ? 'EXPECTED_LINT_FAILURE_REPRODUCED' : 'SCOPED_CHROMIUM_WEBUI_LINT_PASSED', files,
      typed_adapter:typed, skipped_rules:skipped, upstream_sha256:hashes,
      optional_configs:typed ? ['web-component-missing-deps', 'no-explicit-any'] : [],
      chromium_transitive_graph_verified:false};
  } finally {fs.rmSync(temporary, {recursive:true, force:true});}
}
module.exports = {checkLint};
if (require.main === module) {
  const args = process.argv.slice(2);
  const value = name => path.resolve(args[args.indexOf(name) + 1]);
  for (const arg of ['--source-dir', '--rules-dir', '--node-modules']) assert(args.includes(arg));
  const source = value('--source-dir'), modules = value('--node-modules');
  const ts = require(path.join(modules, 'typescript'));
  const files = fs.readdirSync(source, {recursive:true}).filter(file => file.endsWith('.ts'));
  const program = ts.createProgram(files.map(file => path.join(source, file)),
    // Chromium's rules compare rootDir with TypeScript's slash-normalized
    // SourceFile.fileName values, including when the host is Windows.
    {rootDir:source.replaceAll('\\', '/'), target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ESNext,
      moduleResolution:ts.ModuleResolutionKind.Bundler, strict:true, noUncheckedIndexedAccess:true});
  checkLint({source, modules, rulesDir:value('--rules-dir'), program, files})
    .then(async report => {
      const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'arcium-legacy-listeners-'));
      try {
        // Prove that the checker rejects the exact two errors in the native log.
        const file = 'chrome/browser/resources/side_panel/customize_chrome/app.html.ts';
        const target = path.join(fixture, file);
        fs.mkdirSync(path.dirname(target), {recursive:true});
        fs.writeFileSync(target, fs.readFileSync(path.join(source, file), 'utf8')
          .replaceAll('onWorkspaceAppearanceClick_', 'onWorkspaceAppearance_')
          .replaceAll('onCloseWorkspacePanelClick_', 'onCloseWorkspacePanel_'));
        const legacyProgram = ts.createProgram([target], program.getCompilerOptions());
        const proof = await checkLint({source:fixture, modules, rulesDir:value('--rules-dir'),
          program:legacyProgram, files:[file], expectedRules:[
            '@webui-eslint/lit-element-template-structure',
            '@webui-eslint/lit-element-template-structure']});
        report.reported_native_errors_reproduced = proof.status === 'EXPECTED_LINT_FAILURE_REPRODUCED';
      } finally {fs.rmSync(fixture, {recursive:true, force:true});}
      console.log(JSON.stringify(report));
    })
    .catch(error => {console.error(error); process.exitCode = 1;});
}
