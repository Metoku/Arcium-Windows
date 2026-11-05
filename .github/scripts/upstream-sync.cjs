'use strict';

const START = '<!-- arcium-upstream-status:start -->';
const END = '<!-- arcium-upstream-status:end -->';
const PERMISSION_TITLE = 'Enable Actions pull-request creation for upstream sync';

function managedBody(body, status) {
  body = body || '';
  const block = `${START}\n${status}\n${END}`;
  const start = body.indexOf(START);
  const end = body.indexOf(END);
  if (start < 0 && end < 0) return body ? `${body.trimEnd()}\n\n${block}` : block;
  if (start < 0 || end < start || body.indexOf(START, start + 1) >= 0 ||
      body.indexOf(END, end + 1) >= 0) {
    throw new Error('Ambiguous upstream status markers; preserve the existing notes.');
  }
  return body.slice(0, start) + block + body.slice(end + END.length);
}

module.exports = async function monitor({github, context, core}) {
  const {owner, repo} = context.repo;
  const base = context.payload.repository.default_branch;
  const branch = 'automation/arcium-core-update';
  const path = 'upstream/arcium-core.sha';
  const url = `https://github.com/${owner}/${repo}`;
  const compare = `${url}/compare/${encodeURIComponent(base)}...${branch}?expand=1`;
  const summary = ['# Arcium upstream check', ''];
  const revision = value => {
    if (!/^[a-f0-9]{40}$/.test(value)) throw new Error('Invalid upstream revision SHA');
    return value;
  };
  const readPin = file => revision(Buffer.from(file.content, 'base64').toString('utf8').trim());

  try {
    const baseRef = await github.rest.git.getRef({owner, repo, ref: `heads/${base}`});
    const baseSha = revision(baseRef.data.object.sha);
    const baseFile = await github.rest.repos.getContent({owner, repo, path, ref: baseSha});
    const pinned = readPin(baseFile.data);
    const upstream = await github.rest.repos.getCommit({owner: 'dr-baker', repo: 'Arcium', ref: 'main'});
    const latest = revision(upstream.data.sha);
    summary.push(`- Current pin: ${pinned}`, `- Latest Arcium core: ${latest}`, '');
    if (pinned === latest) {
      summary.push('The current pin matches upstream. No candidate changes were needed.');
      return {status: 'CURRENT'};
    }

    let exists = true;
    try {
      await github.rest.git.getRef({owner, repo, ref: `heads/${branch}`});
    } catch (error) {
      if (error.status !== 404) throw error;
      exists = false;
    }
    if (exists) {
      // Preserve candidate history and manual edits. A conflict needs review;
      // never force-reset the branch or modify the installed/default pin.
      try {
        await github.rest.repos.merge({owner, repo, base: branch, head: baseSha,
          commit_message: 'chore: refresh upstream proposal with current Windows integration'});
      } catch (error) {
        if (error.status !== 409) throw error;
        throw new Error(`Candidate merge conflict. Resolve ${compare} before retrying; no forced reset was attempted.`);
      }
    } else {
      await github.rest.git.createRef({owner, repo, ref: `refs/heads/${branch}`, sha: baseSha});
    }

    const candidateFile = await github.rest.repos.getContent({owner, repo, path, ref: branch});
    if (readPin(candidateFile.data) !== latest) {
      await github.rest.repos.createOrUpdateFileContents({owner, repo, path, branch,
        message: `chore: propose Arcium core ${latest.slice(0, 12)}`,
        content: Buffer.from(latest + '\n').toString('base64'), sha: candidateFile.data.sha});
    }

    summary.push(`[Review candidate changes](${compare})`, '');
    // Token-authored commits do not trigger ordinary push/PR checks. A failed
    // explicit dispatch is a failed monitor run, not successful validation.
    await github.rest.actions.createWorkflowDispatch({owner, repo,
      workflow_id: 'validate.yml', ref: branch});
    summary.push(`Source metadata validation requested on ${branch}.`,
      'This request does not establish a browser build or Windows compatibility.', '');

    const proposal = [
      'Review the proposed Arcium core revision.', '',
      `- Current pin: ${pinned}`, `- Proposed revision: ${latest}`,
      `- Windows integration base: ${baseSha}`,
      `- [Upstream changes](https://github.com/dr-baker/Arcium/compare/${pinned}...${latest})`,
      `- [Candidate changes](${compare})`, '',
      'Source metadata validation has been requested. Before merging, verify the',
      'Windows platform/Chromium version pins, patch application and native build.',
      'The monitor does not merge proposals, publish releases or install updates.'
    ].join('\n');
    const prs = await github.rest.pulls.list({owner, repo, state: 'open', base,
      head: `${owner}:${branch}`, per_page: 20});
    if (prs.data.length) {
      const pr = prs.data[0];
      const body = managedBody(pr.body, proposal);
      if (body !== (pr.body || '')) {
        await github.rest.pulls.update({owner, repo, pull_number: pr.number, body});
      }
      summary.push(`Review PR: ${pr.html_url}`);
      return {status: 'PROPOSAL_READY', url: pr.html_url};
    }
    try {
      const pr = await github.rest.pulls.create({owner, repo, base, head: branch,
        title: 'chore: review Arcium core revision', body: managedBody('', proposal), draft: true});
      summary.push(`Draft review PR: ${pr.data.html_url}`);
      return {status: 'PROPOSAL_READY', url: pr.data.html_url};
    } catch (error) {
      if (error.status !== 403 ||
          !/GitHub Actions is not permitted to create or approve pull requests/i.test(error.message)) {
        throw error;
      }
      core.warning('Automatic PR creation is disabled. The candidate and manual review link are available.');
      const status = [
        'Automatic PR creation is blocked by the repository Actions setting.', '',
        `- Current pin: ${pinned}`, `- Proposed revision: ${latest}`,
        `- [Review candidate and create a PR manually](${compare})`,
        `- [Actions settings](${url}/settings/actions)`, '',
        'Under Workflow permissions, enable **Allow GitHub Actions to create and',
        'approve pull requests**, then save. This workflow creates draft proposals;',
        'it does not approve or merge them. You may instead keep manual PR creation.',
        'Source validation was requested separately; inspect its result before review.'
      ].join('\n');
      const issues = await github.paginate(github.rest.issues.listForRepo,
        {owner, repo, state: 'open', per_page: 100});
      const existing = issues.find(issue => !issue.pull_request && issue.title === PERMISSION_TITLE);
      let issueUrl;
      if (existing) {
        const body = managedBody(existing.body, status);
        if (body !== (existing.body || '')) {
          await github.rest.issues.update({owner, repo, issue_number: existing.number, body});
        }
        issueUrl = existing.html_url;
      } else {
        const issue = await github.rest.issues.create({owner, repo,
          title: PERMISSION_TITLE, body: managedBody('', status)});
        issueUrl = issue.data.html_url;
      }
      summary.push('**Automatic PR creation needs the repository permission setting.**',
        `Manual review: ${compare}`, `Permission issue: ${issueUrl}`);
      return {status: 'PERMISSION_REQUIRED', url: compare};
    }
  } catch (error) {
    summary.push(`**Monitor failed:** ${error.message}`);
    throw error;
  } finally {
    await core.summary.addRaw(summary.join('\n') + '\n').write();
  }
};
