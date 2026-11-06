"""Execute the real monitor and workflow hook against an offline GitHub API."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRANCH = 'automation/arcium-core-update'
PINNED, LATEST, BASE = 'a' * 40, 'b' * 40, 'c' * 40

HARNESS = r'''
const fs = require('node:fs');
const path = require('node:path');
const config = JSON.parse(fs.readFileSync(0, 'utf8'));
const calls = [], warnings = [];
let summary = '';
let candidateExists = config.exists !== false;
const pinned = config.pinned || 'a'.repeat(40);
const latest = config.latest || 'b'.repeat(40);
const base = 'c'.repeat(40);
const invoke = (name, fn) => async args => {
  calls.push({name, args});
  return fn(args);
};
function fail(status, message) {throw Object.assign(new Error(message), {status});}
const issues = config.issue ? [config.issue] : [];
const github = {rest: {
  git: {
    getRef: invoke('getRef', args => {
      if (args.ref === 'heads/main') return {data: {object: {sha: base}}};
      if (config.refError) fail(config.refError, 'Candidate reference failed');
      if (!candidateExists) fail(404, 'Not found');
      return {data: {object: {sha: 'd'.repeat(40)}}};
    }),
    createRef: invoke('createRef', () => {candidateExists = true; return {data: {}};})
  },
  repos: {
    getCommit: invoke('getCommit', () => ({data: {sha: latest}})),
    getContent: invoke('getContent', args => ({data: {
      content: Buffer.from((args.ref === base ? pinned : config.candidate || pinned) + '\n').toString('base64'),
      sha: 'e'.repeat(40)
    }})),
    merge: invoke('merge', () => {
      if (config.mergeError) fail(config.mergeError, 'Merge failed');
      return {status: 201, data: {sha: 'f'.repeat(40)}};
    }),
    createOrUpdateFileContents: invoke('writePin', () => ({data: {}}))
  },
  actions: {listWorkflowRuns: invoke('listRuns', args => ({data:{workflow_runs:
    config.workflowRuns?.[args.workflow_id] || []}})),
  createWorkflowDispatch: invoke('dispatch', () => {
    if (config.dispatchError) fail(403, 'Validation dispatch denied');
    return {status: 204};
  })},
  pulls: {
    list: invoke('listPR', () => ({data: config.pr ? [config.pr] : []})),
    update: invoke('updatePR', () => ({data: {}})),
    create: invoke('createPR', () => {
      if (config.prError) fail(config.prError.status, config.prError.message);
      return {data: {number: 42, html_url: 'https://github.com/owner/project/pull/42'}};
    })
  },
  issues: {
    listForRepo: invoke('listIssues', () => ({data: issues})),
    update: invoke('updateIssue', () => ({data: {}})),
    create: invoke('createIssue', () => ({data: {html_url: 'https://github.com/owner/project/issues/28'}}))
  }
}, paginate: async (method, args) => (await method(args)).data};
const context = {repo: {owner: 'owner', repo: 'project'}, payload: {repository: {default_branch: 'main'}}};
const core = {warning: value => warnings.push(value), summary: {
  addRaw(value) {summary += value; return this;},
  async write() {calls.push({name: 'writeSummary'});}
}};
async function run() {
  const monitor = require(path.resolve('.github/scripts/upstream-sync.cjs'));
  let result;
  if (config.workflow) {
    const yaml = fs.readFileSync('.github/workflows/upstream-sync.yml', 'utf8');
    const ending = config.workflowEndings === 'CRLF' ? '\r\n' : '\n';
    const source = yaml.replace(/\r?\n/g, ending);
    const script = source.split(/          script: \|\r?\n/)[1];
    if (!script) throw new Error('Workflow script hook missing');
    const AsyncFunction = Object.getPrototypeOf(async function() {}).constructor;
    await new AsyncFunction('require', 'github', 'context', 'core', script)(
      value => require(path.resolve(value)), github, context, core);
  } else {
    result = await monitor({github, context, core});
  }
  return {result, calls, warnings, summary};
}
run().then(value => process.stdout.write(JSON.stringify(value))).catch(error => {
  process.stdout.write(JSON.stringify({error: error.message, calls, warnings, summary}));
});
'''


@unittest.skipUnless(shutil.which('node'), 'Node.js is required for monitor contracts')
class UpstreamMonitorTests(unittest.TestCase):
    def run_monitor(self, **options):
        result = subprocess.run([shutil.which('node'), '-e', HARNESS],
                                input=json.dumps(options), capture_output=True,
                                text=True, cwd=ROOT, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(sum(c['name'] == 'writeSummary' for c in output['calls']),
                         1, output.get('error', output))
        # All mutating APIs either target the candidate or proposal metadata.
        for call in output['calls']:
            if call['name'] == 'writePin':
                self.assertEqual(call['args']['branch'], BRANCH)
                self.assertEqual(call['args']['path'], 'upstream/arcium-core.sha')
            if call['name'] == 'merge':
                self.assertEqual(call['args']['base'], BRANCH)
                self.assertEqual(call['args']['head'], BASE)
                self.assertNotIn('force', call['args'])
        return output

    def call(self, output, name):
        return [c['args'] for c in output['calls'] if c['name'] == name]

    def test_current_pin_has_no_candidate_or_review_writes(self):
        output = self.run_monitor(latest=PINNED)
        self.assertEqual(output['result']['status'], 'CURRENT')
        for name in ('merge', 'writePin', 'dispatch', 'createRef', 'createPR'):
            self.assertFalse(self.call(output, name))

    def test_existing_candidate_refreshes_from_main_before_updating_and_requesting_checks(self):
        output = self.run_monitor()
        self.assertNotIn('error', output)
        names = [c['name'] for c in output['calls']]
        self.assertLess(names.index('merge'), names.index('writePin'))
        self.assertLess(names.index('writePin'), names.index('dispatch'))
        self.assertLess(names.index('dispatch'), names.index('createPR'))
        self.assertEqual(self.call(output, 'writePin')[0]['sha'], 'e' * 40)
        self.assertEqual(self.call(output, 'dispatch')[0]['ref'], BRANCH)
        self.assertEqual([item['workflow_id'] for item in self.call(output, 'dispatch')],
                         ['validate.yml', 'patch-hunk-compatibility.yml', 'windows-build-experiment.yml'])
        self.assertEqual(self.call(output, 'dispatch')[-1]['inputs'],
                         {'compile_browser':'false', 'runner':'windows-2025'})
        self.assertTrue(self.call(output, 'createPR')[0]['draft'])
        self.assertIn('does not establish a browser build', output['summary'])

    def test_same_candidate_reuses_current_head_validation_and_never_rebuilds_automatically(self):
        workflows = ['validate.yml', 'patch-hunk-compatibility.yml', 'windows-build-experiment.yml']
        runs = {name:[{'id':20,'head_sha':'d' * 40,'status':'completed','conclusion':'success'}]
                for name in workflows}
        output = self.run_monitor(workflowRuns=runs, candidate=LATEST)
        self.assertFalse(self.call(output, 'dispatch'))
        self.assertTrue(all(item['status'] == 'PASSED' for item in output['result']['validations']))
        runs[workflows[-1]][0].update(status='in_progress', conclusion=None)
        running = self.run_monitor(workflowRuns=runs, candidate=LATEST)
        self.assertFalse(self.call(running, 'dispatch'))
        self.assertIn('RUNNING', running['summary'])
        runs[workflows[-1]][0].update(status='completed', conclusion='failure')
        failed = self.run_monitor(workflowRuns=runs, candidate=LATEST)
        self.assertEqual(failed['result']['status'], 'VALIDATION_FAILED')
        self.assertFalse(self.call(failed, 'dispatch'))
        self.assertIn('FAILED', failed['summary'])

    def test_validation_from_another_head_is_not_reused_and_latest_retry_wins(self):
        runs = {'validate.yml':[{'id':20,'head_sha':'a' * 40,'status':'completed','conclusion':'success'}]}
        output = self.run_monitor(workflowRuns=runs)
        self.assertEqual(len(self.call(output, 'dispatch')), 3)
        runs['validate.yml'] = [
            {'id':19,'head_sha':'d' * 40,'status':'completed','conclusion':'failure'},
            {'id':21,'head_sha':'d' * 40,'status':'completed','conclusion':'success'}]
        retried = self.run_monitor(workflowRuns=runs)
        self.assertEqual(retried['result']['validations'][0]['status'], 'PASSED')
        self.assertEqual(len(self.call(retried, 'dispatch')), 2)

    def test_new_candidate_starts_from_the_read_main_snapshot(self):
        output = self.run_monitor(exists=False)
        self.assertEqual(self.call(output, 'createRef')[0]['sha'], BASE)
        self.assertFalse(self.call(output, 'merge'))
        self.assertNotIn('error', output)

    def test_merge_conflict_preserves_candidate_and_stops_other_writes(self):
        output = self.run_monitor(mergeError=409)
        self.assertIn('Candidate merge conflict', output['error'])
        self.assertIn('compare/main...automation/arcium-core-update', output['summary'])
        for name in ('writePin', 'dispatch', 'createPR', 'createRef'):
            self.assertFalse(self.call(output, name))

    def test_permission_denial_reuses_issue_and_preserves_notes_without_repeat_updates(self):
        issue = {'number': 28, 'title': 'Enable Actions pull-request creation for upstream sync',
                 'body': 'Manual owner notes.', 'html_url': 'https://github.com/owner/project/issues/28'}
        denial = {'status': 403, 'message': 'GitHub Actions is not permitted to create or approve pull requests.'}
        output = self.run_monitor(issue=issue, prError=denial)
        self.assertEqual(output['result']['status'], 'PERMISSION_REQUIRED')
        body = self.call(output, 'updateIssue')[0]['body']
        self.assertTrue(body.startswith('Manual owner notes.'))
        self.assertIn('settings/actions', body)
        self.assertIn('Manual review:', output['summary'])
        self.assertFalse(self.call(output, 'createIssue'))
        issue['body'] = body
        repeated = self.run_monitor(issue=issue, prError=denial, candidate=LATEST)
        self.assertFalse(self.call(repeated, 'updateIssue'))
        self.assertFalse(self.call(repeated, 'writePin'))

    def test_permission_denial_creates_one_issue_when_none_exists(self):
        output = self.run_monitor(prError={'status': 403,
            'message': 'GitHub Actions is not permitted to create or approve pull requests.'})
        self.assertEqual(len(self.call(output, 'createIssue')), 1)
        self.assertEqual(output['result']['status'], 'PERMISSION_REQUIRED')

    def test_validation_dispatch_failure_cannot_report_a_ready_proposal(self):
        output = self.run_monitor(dispatchError=True)
        self.assertIn('Validation dispatch denied', output['error'])
        self.assertFalse(self.call(output, 'createPR'))
        self.assertIn('Monitor failed:', output['summary'])

    def test_other_errors_are_not_reported_as_the_pr_permission_setting(self):
        for options in ({'prError': {'status': 403, 'message': 'Resource not accessible'}},
                        {'prError': {'status': 422, 'message': 'Validation failed'}},
                        {'refError': 403}, {'latest': 'invalid'}):
            with self.subTest(options=options):
                output = self.run_monitor(**options)
                self.assertIn('error', output)
                self.assertFalse(self.call(output, 'createIssue'))

    def test_existing_pr_retains_review_notes_and_updates_only_its_managed_status(self):
        pr = {'number': 42, 'body': 'Review notes.', 'html_url': 'https://github.com/owner/project/pull/42'}
        output = self.run_monitor(pr=pr)
        body = self.call(output, 'updatePR')[0]['body']
        self.assertTrue(body.startswith('Review notes.'))
        self.assertIn(LATEST, body)
        self.assertFalse(self.call(output, 'createPR'))
        pr['body'] = body + '\nMore owner notes.'
        repeated = self.run_monitor(pr=pr, candidate=LATEST)
        self.assertFalse(self.call(repeated, 'updatePR'))

    def test_actual_workflow_executes_the_module(self):
        for ending in ('LF', 'CRLF'):
            with self.subTest(ending=ending):
                output = self.run_monitor(workflow=True, workflowEndings=ending)
                self.assertNotIn('error', output)
                self.assertEqual(len(self.call(output, 'createPR')), 1)

    def test_write_capable_workflow_has_no_pull_request_trigger(self):
        workflow = (ROOT / '.github/workflows/upstream-sync.yml').read_text()
        self.assertNotIn('\n  pull_request:', workflow)
        self.assertNotIn('\n  pull_request_target:', workflow)
        self.assertIn('branches: [main]', workflow)
        self.assertIn('persist-credentials: false', workflow)

    def test_damaged_managed_markers_preserve_owner_notes(self):
        pr = {'number': 42, 'body': 'Notes\n<!-- arcium-upstream-status:start -->\nBroken block',
              'html_url': 'https://github.com/owner/project/pull/42'}
        output = self.run_monitor(pr=pr)
        self.assertIn('Ambiguous upstream status markers', output['error'])
        self.assertFalse(self.call(output, 'updatePR'))
