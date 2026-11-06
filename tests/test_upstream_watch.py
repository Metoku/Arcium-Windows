"""Run the actual multi-source watcher against an offline GitHub/VersionHistory API."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
TITLE = 'Upstream update watch: Chromium, Arcium and Xelium'
HARNESS = r'''
const fs = require('node:fs');
const path = require('node:path');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const watch = require(path.resolve('.github/scripts/upstream-watch.cjs'));
const calls = [];
let summary = '';
const corePin = 'a'.repeat(40), windowsPin = 'b'.repeat(40), base = 'c'.repeat(40);
const feature = JSON.parse(fs.readFileSync('upstream/feature-watch.json', 'utf8'));
const files = {'upstream/arcium-core.sha':corePin, 'upstream/helium-windows.sha':windowsPin,
 'upstream/chromium-version.txt':config.engine || '156.0.8078.47',
 'upstream/feature-watch.json':JSON.stringify(config.feature || feature)};
const revisions = {Arcium:corePin, 'Arcium-macOS':feature.arcium_macos,
 'xelium-macos':feature.xelium_macos, 'helium-windows':windowsPin, ...config.revisions};
const invoke = (name, fn) => async args => {calls.push({name, args}); return fn(args);};
const github = {rest:{git:{getRef:invoke('getRef', () => ({data:{object:{sha:base}}}))},
 repos:{getContent:invoke('getContent', args => ({data:{encoding:config.encoding || 'base64',
  content:Buffer.from(files[args.path]).toString('base64')}})),
 getCommit:invoke('getCommit', args => {
  if (config.failedRepo === args.repo) throw new Error('Upstream unavailable');
  return {data:{sha:revisions[args.repo]}};
 })}, issues:{
 listForRepo:invoke('listIssues', () => ({data:config.issues || []})),
 update:invoke('updateIssue', () => ({data:{}})),
 create:invoke('createIssue', () => ({data:{html_url:'https://github.com/owner/project/issues/44'}})),
 }}, paginate:async (method,args) => (await method(args)).data};
const context = {repo:{owner:'owner',repo:'project'},payload:{repository:{default_branch:'main'},inputs:{report_only:config.booleanInput ? !!config.reportOnly : config.reportOnly ? 'true':'false'}}};
const core = {summary:{addRaw(value){summary+=value;return this;},
 async write(){calls.push({name:'writeSummary'});}}};
async function getJson(url) {
 calls.push({name:'fetchVersion',args:{url}});
 if(url!==watch.VERSION_URL)throw new Error('Unknown URL');
 if(config.networkError)throw new Error('VersionHistory unavailable');
 return config.payload || {releases:[{version:config.stable || '158.0.8127.18',fraction:0.01,serving:{}}]};
}
async function run() {
 if(config.compare)return {comparison:watch.compareVersions(...config.compare)};
 if(config.workflow) {
  const yaml=fs.readFileSync('.github/workflows/upstream-watch.yml','utf8');
  const script=yaml.split(/          script: \|\r?\n/)[1];
  if(!script)throw new Error('Missing workflow hook');
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  await new AsyncFunction('require','github','context','core',script)(
   () => options => watch({...options,getJson}),github,context,core);
  return {calls,summary};
 }
 const result=await watch({github,context,core,getJson,reportOnly:!!config.reportOnly});
 return {result,calls,summary};
}
run().then(value => process.stdout.write(JSON.stringify(value)))
 .catch(error => process.stdout.write(JSON.stringify({error:error.message,calls,summary})));
'''


@unittest.skipUnless(shutil.which('node'), 'Node.js is required')
class UpstreamWatchTests(unittest.TestCase):
    def run_watch(self, **options):
        result = subprocess.run([shutil.which('node'), '-e', HARNESS], input=json.dumps(options),
                                text=True, capture_output=True, cwd=ROOT, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = json.loads(result.stdout)
        if not options.get('compare'):
            self.assertEqual(sum(c['name'] == 'writeSummary' for c in output['calls']), 1)
        return output

    def calls(self, output, name):
        return [call['args'] for call in output['calls'] if call['name'] == name]

    def test_stable_engine_and_all_current_baselines_need_no_issue(self):
        output = self.run_watch(stable='156.0.8078.47')
        self.assertEqual(output['result']['status'], 'NO_NEW_UPDATES')
        self.assertFalse(self.calls(output, 'createIssue'))
        self.assertFalse(self.calls(output, 'updateIssue'))
        self.assertTrue(all(c['ref'] == 'c' * 40 for c in self.calls(output, 'getContent')))

    def test_changed_feature_or_platform_is_reviewed_without_changing_pins(self):
        for repo in ('Arcium', 'Arcium-macOS', 'xelium-macos', 'helium-windows'):
            with self.subTest(repo=repo):
                output = self.run_watch(stable='156.0.8078.47', revisions={repo:'f' * 40})
                self.assertEqual(output['result']['status'], 'REVIEW_NEEDED')
                created = self.calls(output, 'createIssue')
                self.assertEqual(len(created), 1)
                self.assertEqual(created[0]['title'], TITLE)
                self.assertIn('/compare/', created[0]['body'])
                self.assertIn('do not mean every feature', created[0]['body'])

    def test_newer_engine_uses_active_rollouts_and_numeric_comparison(self):
        output = self.run_watch(payload={'releases':[
            {'version':'199.0.1.2','fraction':0,'serving':{}},
            {'version':'198.0.1.2','fraction':1,'serving':{'endTime':'2026-01-01T00:00:00Z'}},
            {'version':'158.0.10.1','fraction':0.01,'serving':{}},
            {'version':'158.0.9.100','fraction':1,'serving':{}},
        ]})
        self.assertEqual(output['result']['stable'], '158.0.10.1')
        self.assertEqual(output['result']['status'], 'REVIEW_NEEDED')
        self.assertEqual(self.run_watch(compare=['158.0.10.1','158.0.9.100'])['comparison'], 1)
        ahead = self.run_watch(engine='200.0.1.2', stable='158.0.10.1')
        self.assertEqual(ahead['result']['status'], 'NO_NEW_UPDATES')
        self.assertIn('Ahead of Stable', ahead['summary'])

    def test_report_only_never_reads_or_writes_issues(self):
        output = self.run_watch(reportOnly=True)
        self.assertEqual(output['result']['status'], 'REVIEW_NEEDED')
        for name in ('listIssues', 'createIssue', 'updateIssue'):
            self.assertFalse(self.calls(output, name))

    def test_one_issue_keeps_owner_notes_and_does_not_churn_or_reopen_acknowledged_status(self):
        issue = {'number':44,'title':TITLE,'body':'Owner notes.',
                 'state':'open','html_url':'https://github.com/owner/project/issues/44'}
        first = self.run_watch(issues=[issue])
        body = self.calls(first, 'updateIssue')[0]['body']
        self.assertTrue(body.startswith('Owner notes.'))
        issue['body'] = body
        second = self.run_watch(issues=[issue])
        self.assertFalse(self.calls(second, 'updateIssue'))
        issue['state'] = 'closed'
        acknowledged = self.run_watch(issues=[issue])
        self.assertFalse(self.calls(acknowledged, 'updateIssue'))
        changed = self.run_watch(issues=[issue], stable='159.0.1.2')
        self.assertEqual(self.calls(changed, 'updateIssue')[0]['state'], 'open')

    def test_failures_or_malformed_data_cannot_report_current_or_write_issue(self):
        options = [{'networkError':True}, {'failedRepo':'xelium-macos'},
                   {'revisions':{'Arcium':'bad'}}, {'encoding':'utf8'},
                   {'feature':{'schema':2}}, {'payload':{'releases':[]}},
                   {'payload':{'releases':[{'version':'158.0.1.2','fraction':0}]}},
                   {'payload':{'releases':[{'version':'bad','fraction':1}]}}]
        for option in options:
            with self.subTest(option=option):
                output = self.run_watch(**option)
                self.assertIn('error', output)
                self.assertIn('Watch failed:', output['summary'])
                self.assertFalse(self.calls(output, 'createIssue'))
                self.assertFalse(self.calls(output, 'updateIssue'))

    def test_duplicate_issues_or_broken_markers_are_not_overwritten(self):
        issue = {'number':44,'title':TITLE,'body':'Notes\n<!-- arcium-feature-watch:start -->',
                 'state':'open','html_url':'https://github.com/owner/project/issues/44'}
        for issues in ([issue], [issue, {**issue, 'number':45}]):
            output = self.run_watch(issues=issues)
            self.assertIn('error', output)
            self.assertFalse(self.calls(output, 'updateIssue'))

    def test_workflow_hook_reports_without_writes_and_never_runs_on_untrusted_pr(self):
        for boolean_input in (False, True):
            output = self.run_watch(workflow=True, reportOnly=True, booleanInput=boolean_input)
            self.assertNotIn('error', output)
            self.assertIn('Report only:', output['summary'])
            self.assertFalse(self.calls(output, 'createIssue'))
        workflow = (ROOT / '.github/workflows/upstream-watch.yml').read_text()
        self.assertNotIn('\n  pull_request:', workflow)
        self.assertNotIn('\n  pull_request_target:', workflow)
        self.assertIn('branches: [main]', workflow)
        self.assertIn('contents: read', workflow)
        self.assertIn('persist-credentials: false', workflow)


if __name__ == '__main__':
    unittest.main()
