# Arcium-Windows: faster Windows builds — complete setup

This guide is for **Metoku/Arcium-Windows**. **GitHub currently reports its owner `Metoku` as a personal User account and the repository as public.** This matters: GitHub-hosted larger runners cannot be attached directly to a personal repository, and GitHub warns against attaching a self-hosted runner to a public repository. You must choose a suitable safe route below *before* running the native compile. Automated source checks still run as normal; the expensive full Chromium build is a **manual workflow**.

## 1. What failed, and what the improvements can/cannot do

- [Full Chromium run #41356619052](https://github.com/Metoku/Arcium-Windows/actions/runs/41356619052) compiled about **22,400/81,338 reported build steps** in 310 minutes, then hit its deliberate build timeout. No first C++ error was found; ~121.6 GiB disk remained. No `chrome.exe` and no launch test.
- The original Windows runner had approximately **4 vCPUs and 16 GiB RAM** and the native build used `-j 3`. This was a *cold* compile.
- [PR #29](https://github.com/Metoku/Arcium-Windows/pull/29) added hardware-aware parallelism, progress reporting, fail-fast checks, and a manual Windows workflow using `sccache` to reuse eligible C/C++ compiler outputs across runs.
- **The first build on the new runner can still take hours.** A cache only speeds up later repeated compilations after it contains compatible objects. The new workflow does **not** preserve the entire Chromium source and `out/Default` tree across disposable runners, and cannot guarantee the build finishes within its limit.

## 2. Before you do anything: choose ONE of these two ways to get a runner

**Option A — Paid GitHub-hosted larger runner:** Only available to organizations on **GitHub Team or Enterprise Cloud**. A *personal* GitHub account/repository cannot directly add one, even if your individual account has a paid plan. **Metoku is currently a personal account.** To use this option for Arcium-Windows, you would first need an eligible organization and to **transfer the repository to that organization**, with an explicit decision to accept the changed ownership, access and potential billing. Do not transfer it merely to follow this guide. See [GitHub larger-runner eligibility](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/manage-larger-runners).

**Option B — Self-hosted runner:** A separate dedicated Windows desktop/server or rented Windows VM connected to the repository. Repository-level registration is supported on personal accounts, but **do not attach a self-hosted runner directly to this currently public repository**. Use a **separate private build repository containing an independently maintained copy of the source and workflow** (not a public fork) or change this repository's visibility only after considering the consequences. Always isolate the Windows VM and run trusted workflows only. A private copy requires using *its* settings and workflow; the public repository's variables do not transfer automatically. For a practical speedup, use a **dedicated Windows x64 VM with at least 16 logical CPU threads, 64 GiB physical RAM and 150 GiB free SSD on the workspace drive** (more disk is preferable, ideally 300–600 GiB). A machine with **32 GiB RAM** does not meet this workflow's RAM preflight. See [GitHub's self-hosted runner setup](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners).

> **Safety:** The current Arcium-Windows repository is **public**. GitHub cautions against public-repository self-hosted runners because untrusted pull requests could execute code on the machine. **Do not register a personal desktop or cloud VM directly to the public repository.** Use a separate private build copy with restricted access plus a dedicated disposable Windows VM; do not store personal files, credentials or existing Chrome/Helium profiles on the runner. See [GitHub's self-hosted runner security warning](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners).

**The workflow refuses to compile** if the selected runner has **fewer than 16 logical CPUs, fewer than 56 GiB RAM, or fewer than 145 GiB free on the drive containing `GITHUB_WORKSPACE`**. The slightly lower numerical checks account for OS/reporting differences; choose hardware meeting the recommended 16/64/150 minimum. The default `windows-2025` runner will fail this check quickly.

## 3A. Option A — Create a GitHub larger runner (eligible organizations only)

1. Sign into GitHub with an organization owner account on GitHub Team or Enterprise Cloud. Make sure the repository is owned by that organization (not merely shared with it).
2. Open the organization's GitHub home page, then **Settings → Actions → Runners**.
3. Select **New runner → New GitHub-hosted runner**.
4. Give it a descriptive **Name**, such as `arcium-windows-16core`.
5. Under **Platform**, choose **Windows x64**. Choose a GitHub-owned Windows image such as Windows Server 2025 where available.
6. Under **Size**, choose **16 vCPUs / 64 GB RAM / 600 GB SSD**, or larger. In the concurrency field, a **maximum concurrency of 1** is enough for this project.
7. Select/create a **runner group** that permits the Arcium-Windows repository to use this runner. Click **Create runner**.
8. Confirm repository access: at the organization **Settings → Actions → Runner groups → [the chosen group] → Repository access**, choose **Selected repositories** and include Arcium-Windows, or use the organization's approved access policy.
9. Return to the **Arcium-Windows repository → Actions → Runners** (Management section in the sidebar). Find the new runner, and use **Copy label** (or read its configured label). Copy that **exact label**. You will enter it in section 4; do not guess from the CPU count.
10. Review **GitHub larger-runner billing** before running. Larger-runner minutes are billable; the workflow is manual-only but each launched job can be expensive.

If **New GitHub-hosted runner** is unavailable, do not substitute the small `windows-2025` label. Verify organization eligibility, owner permissions, and runner availability, or use Option B.

Reference: [Create/manage larger runners](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/manage-larger-runners) · [Find a runner label](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/use-larger-runners).

## 3B. Option B — Register a dedicated Windows self-hosted runner

**For the currently public personal repository, this route first requires a separate private build repository or another isolation approach.** The steps below are intended to be followed in **that private build repository**; do not register the runner against the public original.

1. Set up a **dedicated Windows x64** machine/VM with at least **16 logical CPUs, 64 GiB RAM, and 150 GiB free SSD on the workspace drive**. Do not assume a 32-GiB Windows PC will pass.
2. Install **Visual Studio 2022/2026 or compatible Build Tools with the "Desktop development with C++" workload**, including the x64 MSVC toolchain. Also install **Git for Windows**, Python where needed, and **7-Zip**. The workflow installs the official signed Windows SDK 10.0.28000.0 itself, but **does not install Visual Studio**. The pipeline checks the required C++ toolchain before source downloads.
3. In GitHub, open the **private build repository → Settings → Actions → Runners → New self-hosted runner**. Do **not** open the public Arcium-Windows repository's runner-registration page.
4. Select **Windows** and **x64**. GitHub will display PowerShell commands to download/extract the runner and a `config.cmd` command with a short-lived registration token.
5. Open **PowerShell as Administrator** on the **dedicated Windows build machine**, not on the GitHub website. Execute the *exact commands GitHub displays*, in order. **Never publish or paste the registration token in a chat or issue.** If it expires, generate a new one from GitHub.
6. When `config.cmd` asks for additional runner labels, enter a **unique custom label** such as `arcium-win-x64-16core`. If that prompt was skipped, add the label from the runner's GitHub settings. This is an identifier, not a command; choose a label that no other runner uses.
7. Follow GitHub's instructions to start `run.cmd`, or install the Windows runner service if you want it to remain available without keeping a terminal open. Keep the machine powered on and network-connected while a workflow is running.
8. On GitHub, revisit **Settings → Actions → Runners**. The self-hosted runner should appear **Online/Idle** and display the custom label. Copy that exact label for section 4.
9. Keep this machine dedicated to trusted repository code. If the repository is public, evaluate the security warning above before proceeding.

Reference: [Register a self-hosted runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners) · [Assign runner labels](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/apply-labels).

## 4. Tell Arcium-Windows which runner to use (BOTH options)

These are **repository variables**, not repository secrets. Perform the next steps in the repository **that actually owns the build workflow and has permission to run the selected runner**: Arcium-Windows after an organization transfer under Option A, or your separate private build repository under Option B.

1. Open the **chosen build repository** on GitHub. The current original project is [Metoku/Arcium-Windows](https://github.com/Metoku/Arcium-Windows), but for Option A its owner would change after a transfer; for Option B use your **private** build copy.
2. Click **Settings** at the top of the repository.
3. In the left sidebar under **Security**, open **Secrets and variables → Actions**.
4. Select the **Variables** tab (not Secrets).
5. Click **New repository variable**.
6. In **Name**, paste exactly: `ARCIUM_NATIVE_WINDOWS_RUNNER`.
7. In **Value**, paste the **exact runner label copied from section 3A or 3B**. Examples: `arcium-windows-16core` (organization larger runner) or `arcium-win-x64-16core` (dedicated self-hosted runner). **Examples are not automatically available labels.**
8. Click **Add variable**. Review it in the Variables table. Do not add `self-hosted, windows, x64` as comma-separated text: the current workflow expects **one uniquely identifying label**.

The workflow's key configuration (already stored in the repository) is:

```yaml
runs-on: ${{ vars.ARCIUM_NATIVE_WINDOWS_RUNNER || 'windows-2025' }}
```

If the variable is missing, it picks the small Windows 2025 runner and intentionally **fails the resource check before downloading Chromium**. This is a guardrail, not an alternative fast build.

Reference: [Create a repository variable](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-variables).

## 5. Run the new workflow — only after section 4

1. Open the **same repository where you set `ARCIUM_NATIVE_WINDOWS_RUNNER` → Actions**.
2. In the left workflow list, click **Native Windows Chrome-only build (cached, high-capacity)**. It is **not** the previous one-time experiment `full-chrome-sdk-28000.yml`.
3. Click **Run workflow** on the right, select **main**, then click the green **Run workflow** button.
4. Open the new workflow run, then the **Compile chrome with SDK 28000 and reusable sccache** job.
5. Check the first steps. **Check CPU, RAM and disk** must pass, followed by **Confirm Visual Studio desktop C++ build tools exist**. If either fails, fix the selected runner instead of rerunning the build.
6. Wait for **Install official Microsoft-signed SDK 28000**, then **Stage pinned Helium-Windows and Arcium patches**, then **Compile native chrome with sccache and hardware-aware parallelism**. During compilation, the log prints *elapsed time, remaining disk space and the latest available Siso step counts*.
7. Only if compilation succeeds does **Headless launch with disposable user-data directory** run. Successful compilation alone is not proof the browser UI works.
8. Review **Show sccache hits and misses** near the end, and download **arcium-cached-windows-chrome-diagnostics** from the run's **Artifacts** section. Check `browser-only-build.json` for the actual result and `browser-only-build.log` for compiler errors. Browser binaries are **not** uploaded.

If the **Run workflow** button is absent: ensure you are viewing the workflow from **main**, Actions are enabled, and your GitHub account has write access. This workflow is `workflow_dispatch`-only, so it **never starts automatically**.

Reference: [Manually run GitHub Actions workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## 6. Quick troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| "No runner matching the labels" / job queued indefinitely | Wrong label, offline self-hosted runner, or runner group blocks repository | Compare `ARCIUM_NATIVE_WINDOWS_RUNNER` with the exact label under **Actions → Runners**; verify Online/Idle and repository access |
| "Underpowered native Chromium runner" | Less than 16 logical CPUs, 56 GiB reported RAM or 145 GiB free workspace disk | Choose/provision a stronger runner. Do not relabel a 4-core or 32-GB machine |
| "Visual Studio Build Tools are missing" / "Missing MSVC x64 toolchain" | Self-hosted machine lacks C++ compiler | Install Visual Studio desktop C++ tools and rerun |
| Cache missing / `sccache` missing | Cache tool not installed or PATH not set | Inspect "Install persistent compiler cache" and "Verify the compiler cache exists" logs; do not run an uncached build |
| `sccache` shows many misses on the first run | The cache is cold; that is expected | Compare stats on later builds with unchanged source/compiler/flags; cache reuse isn't guaranteed |
| Build shows `TIMEOUT` | Full Chromium build could not finish within configured bound | Examine final Ninja counts; consider 32 cores/128 GiB or a long-lived trusted builder with actual incremental source/output reuse |
| No `chrome.exe` | Compile not complete or failed | Examine actual result log; never report that the browser works from GN alone |

## 7. Important limitations

- **No actual full incremental source/output reuse yet.** Each fresh GitHub-hosted runner downloads patches/Chromium and generates GN again. The build adapter rejects an existing pre-patched source tree to avoid applying all 551 patches twice. `sccache` caches eligible *compiler outputs only*.
- The GitHub Actions compiler cache may experience limits, throttling, and eviction. Even a larger runner does not guarantee that the first build will finish.
- Never bypass Windows SDK 28000: pinned Chromium 156 requires it for native compilation.
- Avoid storing browser profiles, personal secrets, or unrelated documents on a public-repository self-hosted runner.
- If you do not have access to either a suitable organization larger runner or a dedicated powerful VM, **stop here**. The new workflow correctly prevents wasting another full hosted build.

This workflow is a compilation experiment; no Windows browser binary, installed application or successful full UI has yet been verified.
