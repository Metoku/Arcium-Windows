/* Check patched appearance CSS with Chromium's pinned stylelint rules. */
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const args = process.argv.slice(2);
function arg(name) {
  assert(args.includes(name), 'Missing ' + name);
  return path.resolve(args[args.indexOf(name) + 1]);
}
(async () => {
  const source = arg('--source-dir');
  const modules = arg('--node-modules');
  const configPath = arg('--config');
  const manifest = name => JSON.parse(fs.readFileSync(path.join(modules, name, 'package.json'), 'utf8'));
  const packageInfo = manifest('stylelint');
  assert.equal(packageInfo.version, '17.0.0');
  assert.equal(manifest('@stylistic/stylelint-plugin').version, '5.0.0');
  assert.equal(manifest('postcss').version, '8.5.3');
  const {default: stylelint} = await import(pathToFileURL(path.join(modules, 'stylelint', packageInfo.exports['.'].default)).href);
  const {default: chromiumConfig} = await import(pathToFileURL(configPath).href);
  // Only module resolution changes; every rule comes from the pinned source.
  const config = {...chromiumConfig,
    plugins:[path.join(modules, '@stylistic/stylelint-plugin/lib/index.js')]};
  const target = path.join(source, 'chrome/browser/resources/settings/appearance_page/appearance_layout_page.css');
  const result = await stylelint.lint({code:fs.readFileSync(target, 'utf8'),codeFilename:target,config});
  const messages = result.results.flatMap(file => file.warnings);
  if (result.errored) throw new Error(JSON.stringify(messages, null, 2));
  assert.equal(messages.length, 0);
  console.log(JSON.stringify({status:'CHROMIUM_APPEARANCE_STYLELINT_PASSED',
    stylelint:packageInfo.version,config_sha256:crypto.createHash('sha256')
      .update(fs.readFileSync(configPath)).digest('hex'),warnings:messages.length}));
})().catch(error => {console.error(error);process.exitCode=1;});
