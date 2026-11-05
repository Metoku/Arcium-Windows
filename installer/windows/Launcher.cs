using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("Arcium")]
[assembly: AssemblyDescription("Arcium for Windows launcher")]

internal static class Launcher {
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)]
    private static extern uint GetPrivateProfileString(string section, string key, string fallback,
        StringBuilder result, uint length, string filename);

    private static string ReadValue(string root, string key) {
        StringBuilder text = new StringBuilder(1024);
        GetPrivateProfileString("Install", key, "", text, (uint)text.Capacity,
            Path.Combine(root, "arcium-install.ini"));
        return text.ToString();
    }

    // Windows CommandLineToArgvW/CRT quoting, including embedded quotes and
    // trailing backslashes. No shell or command-file expansion is involved.
    internal static string Quote(string value) {
        StringBuilder result = new StringBuilder("\"");
        int slashes = 0;
        foreach (char ch in value) {
            if (ch == '\\') { slashes++; continue; }
            if (ch == '"') {
                result.Append('\\', slashes * 2 + 1);
                result.Append('"');
            } else {
                result.Append('\\', slashes);
                result.Append(ch);
            }
            slashes = 0;
        }
        result.Append('\\', slashes * 2);
        return result.Append('"').ToString();
    }

    [STAThread]
    private static int Main(string[] args) {
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            if (ReadValue(root, "Schema") != "1" ||
                ReadValue(root, "Repository") != "Metoku/Arcium-Windows")
                throw new InvalidOperationException("This folder is not a managed Arcium installation.");
            if (args.Length == 1 && args[0] == "--check-for-updates") {
                string script = Path.Combine(root, "tools", "Update-Arcium.ps1");
                ProcessStartInfo update = new ProcessStartInfo(
                    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                        "WindowsPowerShell", "v1.0", "powershell.exe"));
                update.Arguments = "-NoLogo -NoProfile -NonInteractive -STA -ExecutionPolicy Bypass -File " + Quote(script);
                update.UseShellExecute = false;
                update.CreateNoWindow = true;
                // A calling PowerShell 7 session must not redirect PowerShell
                // 5.1's module discovery to its own module directories.
                update.EnvironmentVariables.Remove("PSModulePath");
                // Detach: setup must be able to replace this launcher while the
                // separate updater waits for setup to finish.
                using (Process process = Process.Start(update)) { return 0; }
            }
            string version = ReadValue(root, "Version");
            if (!Regex.IsMatch(version, @"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$"))
                throw new InvalidOperationException("Invalid installed version.");
            string browser = Path.Combine(root, "versions", version, "chrome.exe");
            if (!File.Exists(browser)) throw new FileNotFoundException("The installed browser is missing. Run setup again.");
            StringBuilder arguments = new StringBuilder();
            foreach (string arg in args) { if (arguments.Length > 0) arguments.Append(' '); arguments.Append(Quote(arg)); }
            ProcessStartInfo start = new ProcessStartInfo(browser, arguments.ToString());
            start.WorkingDirectory = Path.GetDirectoryName(browser);
            start.UseShellExecute = false;
            using (Mutex running = new Mutex(false, @"Local\Arcium.Windows.Running"))
            using (Process process = Process.Start(start)) {
                process.WaitForExit();
                return process.ExitCode;
            }
        } catch (Exception ex) {
            MessageBox.Show(ex.Message, "Arcium", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
