'use strict';

const TITLE = 'Upstream update watch: Chromium, Arcium and Xelium';
const START = '<!-- arcium-feature-watch:start -->';
const END = '<!-- arcium-feature-watch:end -->';
const VERSION_URL = 'https://versionhistory.googleapis.com/v1/chrome/platforms/win64/channels/stable/versions/all/releases?filter=endtime=none&order_by=version%20desc';
const revision = value => {
  if (typeof value !== 'string' || !/^[a-f0-9]{40}$/.test(value)) {
    throw new Error('Invalid upstream revision SHA');
  }
  return value;
};
const version = value => {
  if (typeof value !== 'string' || !/^\d+\.\d+\.\d+\.\d+$/.test(value) ||
      value.split('.').some(n => !Number.isSafeInteger(Number(n)))) {
    throw new Error('Invalid Chromium version');
  }
  return value;
};
function compareVersions(left, right) {
  const a = version(left).split('.').map(Number);
  const b = version(right).split('.').map(Number);
  for (let i = 0; i < 4; i++) if (a[i] !== b[i]) return Math.sign(a[i] - b[i]);
  return 0;
}
function activeStable(payload) {
  if (!Array.isArray(payload?.releases) || !payload.releases.length) {
    throw new Error('VersionHistory returned no releases');
  }
  const active = payload.releases.filter(item => {
    version(item.version);
    if (typeof item.fraction !== 'number' || !Number.isFinite(item.fraction) ||
        item.fraction < 0 || item.fraction > 1) throw new Error('Invalid release fraction');
    const end = item.serving?.endTime;
    return item.fraction > 0 && (!end || end === '1970-01-01T00:00:00Z');
  });
  if (!active.length) throw new Error('VersionHistory returned no actively served Stable release');
  return active.map(item => item.version).sort(compareVersions).at(-1);
}
async function fetchJson(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(20000), redirect: 'error'});
  if (!response.ok) throw new Error(`VersionHistory HTTP ${response.status}`);
  const text = await response.text();
  if (text.length > 2 * 1024 * 1024) throw new Error('VersionHistory response is too large');
  return JSON.parse(text);
}
function managedBody(body, status) {
  body = body || '';
  const block = `${START}\n${status}\n${END}`;
  const start = body.indexOf(START), end = body.indexOf(END);
  if (start < 0 && end < 0) return body ? `${body.trimEnd()}\n\n${block}` : block;
  if (start < 0 || end < start || body.indexOf(START, start + 1) >= 0 ||
      body.indexOf(END, end + 1) >= 0) {
    throw new Error('Ambiguous watch markers; preserve the owner notes');
  }
  return body.slice(0, start) + block + body.slice(end + END.length);
}

module.exports = async function watch({github, context, core, reportOnly = false,
  getJson = fetchJson}) {
  const {owner, repo} = context.repo;
  const summary = ['# Engine and feature update watch', ''];
  try {
    const base = context.payload.repository.default_branch;
    const head = await github.rest.git.getRef({owner, repo, ref: `heads/${base}`});
    const ref = revision(head.data.object.sha);
    const read = async path => {
      const file = await github.rest.repos.getContent({owner, repo, path, ref});
      if (file.data.encoding !== 'base64' || typeof file.data.content !== 'string') {
        throw new Error(`Invalid tracked file: ${path}`);
      }
      return Buffer.from(file.data.content, 'base64').toString('utf8').trim();
    };
    const [corePin, windowsPin, engine, configText] = await Promise.all([
      read('upstream/arcium-core.sha'), read('upstream/helium-windows.sha'),
      read('upstream/chromium-version.txt'), read('upstream/feature-watch.json')]);
    revision(corePin); revision(windowsPin); version(engine);
    const config = JSON.parse(configText);
    if (config.schema !== 1 || Object.keys(config).sort().join(',') !==
        'arcium_macos,schema,xelium_macos') throw new Error('Unknown feature-watch schema');
    const sources = [
      {label:'Arcium core', owner:'dr-baker', repo:'Arcium', baseline:corePin},
      {label:'Arcium macOS', owner:'dr-baker', repo:'Arcium-macOS', baseline:revision(config.arcium_macos)},
      {label:'Xelium macOS', owner:'minervanet', repo:'xelium-macos', baseline:revision(config.xelium_macos)},
      {label:'Windows platform', owner:'imputnet', repo:'helium-windows', baseline:windowsPin},
    ];
    const responses = await Promise.allSettled([
      ...sources.map(async source => {
        const commit = await github.rest.repos.getCommit({owner:source.owner, repo:source.repo, ref:'main'});
        return revision(commit.data.sha);
      }), getJson(VERSION_URL).then(activeStable),
    ]);
    const errors = responses.flatMap((response, index) => response.status === 'rejected' ?
      [`${sources[index]?.label || 'Chrome Stable'}: ${response.reason.message}`] : []);
    if (errors.length) throw new Error(errors.join('; '));
    const latest = responses.slice(0, 4).map(response => response.value);
    const stable = responses[4].value;
    const relation = compareVersions(engine, stable);
    const changed = sources.some((source, index) => source.baseline !== latest[index]);
    const pending = changed || relation < 0;
    const rows = sources.map((source, index) => {
      const url = `https://github.com/${source.owner}/${source.repo}`;
      const comparison = `${url}/compare/${source.baseline}...${latest[index]}`;
      const status = source.baseline === latest[index] ? 'Matches watch baseline' :
        `[Changes to review](${comparison})`;
      return `| ${source.label} | \`${source.baseline}\` | \`${latest[index]}\` | ${status} |`;
    });
    const engineStatus = relation < 0 ? 'Newer Stable baseline: review engine compatibility' :
      relation === 0 ? 'Matches Stable baseline' : 'Ahead of Stable baseline; review upstream compatibility';
    const status = [
      '## Source status', '', '| Source | Tracked baseline | Current upstream | Review |',
      '|---|---|---|---|', ...rows,
      `| Chrome Stable, Windows x64 | \`${engine}\` | \`${stable}\` | ${engineStatus} |`, '',
      'Chrome Stable is a release baseline, not proof that any Chromium revision is',
      'compatible with this fork or a complete security assessment.', '',
      'Mac watch baselines record where monitoring started or was acknowledged;',
      'they do not mean every feature at those revisions was ported to Windows.', '',
      '## Next steps', '',
      '1. Review the Arcium core proposal and pair its Chromium/Windows platform pins.',
      '2. Review Mac changes individually; port useful features to Windows when needed.',
      '3. Pass source checks, then compile and test a fresh Windows runtime.',
      '4. Package that runtime and publish its tested Windows installer and checksums.', '',
      `[Update procedure](https://github.com/${owner}/${repo}/blob/${base}/docs/automation.md)`, '',
      'This watch does not change source pins, merge patches, compile, publish,',
      'install or claim that features have already reached the installed browser.',
    ].join('\n');
    summary.push(status);
    let issueUrl = null;
    if (!reportOnly) {
      const issues = await github.paginate(github.rest.issues.listForRepo,
        {owner, repo, state:'all', per_page:100});
      const matches = issues.filter(issue => !issue.pull_request && issue.title === TITLE);
      if (matches.length > 1) throw new Error('Multiple watch issues exist; resolve them without overwriting notes');
      const existing = matches[0];
      if (existing) {
        const body = managedBody(existing.body, status);
        const reopen = existing.state === 'closed' && pending && body !== (existing.body || '');
        if (body !== (existing.body || '') || reopen) {
          await github.rest.issues.update({owner, repo, issue_number:existing.number,
            body, ...(reopen ? {state:'open'} : {})});
        }
        issueUrl = existing.html_url;
      } else if (pending) {
        const issue = await github.rest.issues.create({owner, repo, title:TITLE,
          body:managedBody('', status)});
        issueUrl = issue.data.html_url;
      }
    }
    if (reportOnly) summary.push('', '**Report only:** no issue was created or updated.');
    if (issueUrl) summary.push('', `Watch issue: ${issueUrl}`);
    return {status:pending ? 'REVIEW_NEEDED' : 'NO_NEW_UPDATES', engine, stable, latest, issueUrl};
  } catch (error) {
    summary.push('', `**Watch failed:** ${error.message}`);
    throw error;
  } finally {
    await core.summary.addRaw(summary.join('\n') + '\n').write();
  }
};
module.exports.compareVersions = compareVersions;
module.exports.activeStable = activeStable;
module.exports.VERSION_URL = VERSION_URL;
