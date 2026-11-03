/* Exercise the actual patched Settings methods with a small WebUI contract host.
 * This does not provide Chromium's transitive type checking or a browser render.
 */
'use strict';
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const args = process.argv.slice(2);
const value = name => args[args.indexOf(name) + 1];
if (!args.includes('--source-dir') || !args.includes('--typescript')) {
  throw new Error('Use --source-dir PATH --typescript PATH_TO_TYPESCRIPT_MODULE');
}
const source = path.resolve(value('--source-dir'));
const ts = require(path.resolve(value('--typescript')));
const layoutDir = 'chrome/browser/resources/settings/appearance_page/';
const read = file => fs.readFileSync(path.join(source, file), 'utf8');
const layout = read(layoutDir + 'appearance_layout_page.ts');
const template = read(layoutDir + 'appearance_layout_page.html.ts');
const panel = read('chrome/browser/resources/side_panel/customize_chrome/app.ts');
const panelTemplate = read('chrome/browser/resources/side_panel/customize_chrome/app.html.ts');
let request;
let accept = true;
let pending = null;
let registrations = new Map();
const initial = () => ({
  available: true, spaceId: 'space-a', name: 'Space A', spaces: [{id: 'space-a', name: 'Space A'}],
  chrome: {enabled: true, material: 'auto', materialOpacity: 0.7, colorEffect: 'glows', tintColor: '#112233', tintStrength: 0.6,
    points: [{id: 'first', color: '#ff0000', x: 0.1, y: 0.2, radius: 0.5, opacity: 0.8},
             {id: 'second', color: '#0000ff', x: 0.9, y: 0.8, radius: 0.6, opacity: 0.7}]},
  palette: {controlsChroma: 1, panelsChroma: 0.35, renderingActive: true}, mode: 0, webMode: 0,
  surface: 'glass', tuning: {textOpacity: 0.05, textTint: 0.4, panelOpacity: 0.2, panelTint: 0.6},
  frame: {shadowMode: 'default', borderWidth: 0, blur: 24, opacity: 20},
  preferences: Object.fromEntries(['frameWidth', 'sidebarWidth', 'scale', 'roundedFrame', 'sidebarNavigation', 'collapseStyle']
    .map(key => [key, {value: 1, editable: true}]))});
let state = initial();
const copy = v => JSON.parse(JSON.stringify(v));
class Element {
  isConnected = true;
  mirrorPrefs() {}
  addWebUiListener() {}
  connectedCallback() {}
  disconnectedCallback() {}
}
const html = (strings, ...values) => strings.reduce((text, part, i) => text + part +
  (i < values.length ? (Array.isArray(values[i]) ? values[i].join('') : values[i] ?? '') : ''), '');
const loadTimeData = {getString: key => key, getBoolean: () => true};
const mockRequire = name => {
  if (name.includes('lit.rollup')) return {CrLitElement: Element, html};
  if (name.includes('i18n_setup') || name.includes('load_time_data')) return {loadTimeData};
  if (name.includes('pref_service_observer')) return {PrefServiceObserverMixinLit: base => base};
  if (name.includes('web_ui_listener_mixin')) return {WebUiListenerMixinLit: base => base};
  if (name.includes('cr.js')) return {sendWithPromise: async (name, payload) => {
    if (name === 'getArciumAppearance') return copy(state);
    assert.equal(name, 'setArciumAppearance'); request = payload;
    return pending ? pending : accept;
  }};
  if (name.endsWith('.css.js')) return {getCss: () => ''};
  if (name.endsWith('.html.js')) return {getHtml: () => ''};
  return {};
};
function transpile(text, filename) {
  const result = ts.transpileModule(text, {fileName: filename, reportDiagnostics: true,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}});
  assert.equal((result.diagnostics ?? []).filter(d => d.category === ts.DiagnosticCategory.Error).length, 0,
    'TypeScript syntax diagnostics in ' + filename);
  return result.outputText;
}
function evaluate(text, filename) {
  const exports = {};
  vm.runInNewContext(transpile(text, filename), {exports, require: mockRequire, console,
    chrome: {settingsPrivate: {PrefType: {BOOLEAN: 'boolean'}}}, crypto,
    customElements: {define: (name, ctor) => registrations.set(name, ctor)}});
  return exports;
}
// Type-check the new Settings fields and handlers with typed WebUI adapters.
// The real Chromium dependency graph remains a separate compilation gate.
function checkIsolatedTypes() {
  const os = require('node:os');
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'arcium-appearance-types-'));
  try {
    const rewrite = text => text
      .replaceAll("'/shared/settings/prefs2/pref_service_observer_mixin_lit.js'", "'fixture-prefs'")
      .replaceAll("'//resources/lit/v3_0/lit.rollup.js'", "'fixture-lit'");
    fs.writeFileSync(path.join(temporary, 'appearance_layout_page.ts'), rewrite(layout));
    fs.writeFileSync(path.join(temporary, 'appearance_layout_page.html.ts'), rewrite(template));
    fs.writeFileSync(path.join(temporary, 'stubs.d.ts'), `
      declare namespace chrome.settingsPrivate {
        interface PrefObject<T> {key:string;type:unknown;value:T;}
        enum PrefType {BOOLEAN}
      }
      declare module 'chrome://resources/lit/v3_0/lit.rollup.js' {
        export class CrLitElement extends HTMLElement {
          static get styles():unknown;static get properties():unknown;
          render():unknown;connectedCallback():void;disconnectedCallback():void;
        }
      }
      declare module 'fixture-lit' {export function html(strings:TemplateStringsArray,...values:unknown[]):unknown;}
      declare module 'fixture-prefs' {
        export function PrefServiceObserverMixinLit<T extends new (...args:any[])=>HTMLElement>(base:T):
          T & (new (...args:any[])=>{mirrorPrefs(names:Record<string,string>):void;});
      }
      declare module 'chrome://resources/cr_elements/web_ui_listener_mixin_lit.js' {
        export function WebUiListenerMixinLit<T extends new (...args:any[])=>HTMLElement>(base:T):
          T & (new (...args:any[])=>{addWebUiListener(event:string,callback:()=>void):void;});
      }
      declare module 'chrome://resources/js/cr.js' {export function sendWithPromise<T>(name:string,...args:unknown[]):Promise<T>;}
      declare module '*i18n_setup.js' {export const loadTimeData:{getString(key:string):string;getBoolean(key:string):boolean};}
      declare module '*.css.js' {export function getCss():unknown;}
    `);
    const program = ts.createProgram(['appearance_layout_page.ts', 'appearance_layout_page.html.ts', 'stubs.d.ts']
      .map(file => path.join(temporary, file)), {strict:true,noEmit:true,noUncheckedIndexedAccess:true,
        target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,moduleResolution:ts.ModuleResolutionKind.Bundler,
        lib:['lib.es2022.d.ts','lib.dom.d.ts']});
    const errors = ts.getPreEmitDiagnostics(program);
    assert.equal(errors.length, 0, errors.map(d => ts.flattenDiagnosticMessageText(d.messageText,'\n')).join('\n'));
  } finally {fs.rmSync(temporary,{recursive:true,force:true});}
}
checkIsolatedTypes();
const Layout = evaluate(layout, 'appearance_layout_page.ts').SettingsAppearanceLayoutPageElement;
const getHtml = evaluate(template, 'appearance_layout_page.html.ts').getHtml;
transpile(panel, 'customize_chrome_app.ts');
transpile(panelTemplate, 'customize_chrome_app.html.ts');
const create = () => {const element = new Layout(); element.workspace_ = copy(state); return element;};
const change = (element, action, key, input, kind) => element.onWorkspaceChange_({currentTarget:
  {dataset: {action, key, kind}, value: String(input), checked: input}});
const settle = async () => {for (let i=0; i<8; i++) await Promise.resolve();};
const tests = [];
async function test(name, body) {
  request = null; accept = true; pending = null; state = initial();
  await body(); tests.push(name);
}
(async () => {
  await test('color commits a Space tint without rewriting unrelated recipe fields', async () => {
    const el = create(); change(el, 'chrome', 'tintColor', '#aabbcc'); await settle();
    assert.equal(request.spaceId, 'space-a'); assert.equal(request.action, 'chrome');
    assert.deepEqual(copy(request.value), {tintColor: '#aabbcc', colorEffect: 'tint', enabled: true});
  });
  await test('material enables the requested native window appearance', async () => {
    const el = create(); change(el, 'chrome', 'material', 'frosted'); await settle();
    assert.deepEqual(copy(request.value), {material: 'frosted', enabled: true});
  });
  await test('glow edits preserve IDs and untouched points', async () => {
    const el = create(); el.onWorkspaceGlow_({currentTarget: {dataset: {index: '1', key: 'x'}, value: '0.4'}});
    await settle(); assert.equal(request.value.points[0].id, 'first');
    assert.equal(request.value.points[0].x, 0.1); assert.equal(request.value.points[1].id, 'second');
    assert.equal(request.value.points[1].x, 0.4);
  });
  await test('glow count is bounded and deletion targets only the chosen point', async () => {
    const el = create(); el.workspace_.chrome.points.push(copy(state.chrome.points[0]), copy(state.chrome.points[0]));
    el.onAddWorkspaceGlow_(); assert.equal(request, null);
    el.onRemoveWorkspaceGlow_({currentTarget: {dataset: {index: '1'}}}); await settle();
    assert.equal(request.value.points.length, 3); assert.equal(request.value.points[0].id, 'first');
  });
  await test('new glow gets a unique ID and selects the gradient effect', async () => {
    const el = create(); el.onAddWorkspaceGlow_(); await settle();
    assert.equal(request.value.points.length, 3); assert.notEqual(request.value.points[2].id, 'first');
    assert.equal(request.value.colorEffect, 'glows');
  });
  await test('chroma passes only the two validated model fields', async () => {
    const el = create(); change(el, 'chroma', 'panelsChroma', 0.8, 'number'); await settle();
    assert.deepEqual(copy(request.value), {controlsChroma: 1, panelsChroma: 0.8});
  });
  await test('layout preference preserves its numeric type', async () => {
    const el = create(); change(el, 'pref', 'sidebarWidth', 220, 'number'); await settle();
    assert.deepEqual(copy(request.value), {name: 'sidebarWidth', value: 220});
  });
  await test('a pending save prevents another mutation', async () => {
    const el = create(); let release; pending = new Promise(resolve => {release=resolve;});
    change(el, 'pref', 'sidebarWidth', 220, 'number');
    const first=request; change(el, 'pref', 'scale', 120, 'number'); assert.equal(request, first);
    release(true); await settle(); assert.equal(el.workspaceBusy_, false);
  });
  await test('native rejection is visible and reloads the saved values', async () => {
    const el = create(); accept=false; change(el, 'chrome', 'tintColor', '#ffffff'); await settle();
    assert.equal(el.workspaceStatus_, 'workspaceError'); assert.equal(el.workspace_.chrome.tintColor, '#112233');
  });
  await test('detached component ignores a late snapshot', async () => {
    const el = create(); el.isConnected=false; el.workspace_=null; await el.refreshWorkspace_();
    assert.equal(el.workspace_, null);
  });
  await test('workspace template exposes named controls and a truthful active/fallback state', async () => {
    const text = getHtml.call(create());
    for (const id of ['appearanceSpace', 'workspacePreset', 'workspaceColor']) assert.match(text, new RegExp('id="'+id+'"'));
    assert.match(text, /workspaceGlassFallback/); assert.match(text, /value="frosted"/);
    assert.match(text, /role="status"/);
  });
  // Run the exact panel handler methods rather than copies of their behavior.
  const parsed = ts.createSourceFile('app.ts', panel, ts.ScriptTarget.Latest, true);
  const appClass = parsed.statements.find(s => ts.isClassDeclaration(s) && s.name?.text === 'AppElement');
  const method = name => appClass.members.find(m => m.name?.getText(parsed) === name);
  const body = name => method(name).body.getText(parsed);
  await test('panel Close invokes the Mojo close action', async () => {
    let closed=0;
    const fn = vm.runInNewContext('(function()'+body('onCloseWorkspacePanel_')+')');
    fn.call({apiProxy_: {handler: {closePanel: () => closed++}}}); assert.equal(closed, 1);
  });
  await test('panel appearance button opens the shared editor', async () => {
    let opened=0;
    const fn = vm.runInNewContext('(function()'+body('onWorkspaceAppearance_')+')');
    fn.call({apiProxy_: {handler: {openWorkspaceAppearance: () => opened++}}}); assert.equal(opened, 1);
  });
  await test('Escape closes the panel but respects composing or handled keys', async () => {
    const init = method('onWorkspacePanelKeyDown_').initializer.getText(parsed);
    const expression = transpile('const callback = '+init+'; exports.callback=callback;', 'escape.ts');
    let closed=0;const exports={};
    vm.runInNewContext('(function(){'+expression+'}).call(host)', {exports,host:{onCloseWorkspacePanel_:()=>closed++}});
    const event = {key:'Escape',defaultPrevented:false,isComposing:false,preventDefault(){},stopPropagation(){}};
    exports.callback(event); assert.equal(closed,1);
    exports.callback({...event,defaultPrevented:true}); exports.callback({...event,isComposing:true});
    assert.equal(closed,1);
  });
  console.log(JSON.stringify({status:'ISOLATED_WEBUI_CONTRACTS_PASSED',tests,
    typescript:ts.version,isolated_strict_types_verified:true,browser_render_verified:false,chromium_transitive_types_verified:false}));
})().catch(error => {console.error(error);process.exitCode=1;});
