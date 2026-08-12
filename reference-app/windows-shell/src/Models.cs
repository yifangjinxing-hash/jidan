using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace JidanOS
{
    public sealed class SystemProfile
    {
        public string Id { get; set; }
        public string Name { get; set; }
        public string Subtitle { get; set; }
        public string Engine { get; set; }
        public string Status { get; set; }
        public string Tone { get; set; }
        public string Accent { get; set; }
        public bool CanBoot { get; set; }
        public ArtifactKind FilterKind { get; set; }

        public SystemProfile(string id, string name, string subtitle, string engine, string status, string tone, string accent, bool canBoot, ArtifactKind filterKind)
        {
            Id = id;
            Name = name;
            Subtitle = subtitle;
            Engine = engine;
            Status = status;
            Tone = tone;
            Accent = accent;
            CanBoot = canBoot;
            FilterKind = filterKind;
        }
    }

    public static class SystemCatalog
    {
        public static List<SystemProfile> Detect()
        {
            string adbPath = RuntimeUtil.FindAndroidAdb();
            bool adb = adbPath != null && RuntimeUtil.HasAdbDevice(adbPath);
            List<SystemProfile> profiles = new List<SystemProfile>();
            profiles.Add(new SystemProfile("jidan", "Jidan", "统一成品包系统", "Universal Router", "可启动", "ready", "#B9FF57", true, ArtifactKind.Unknown));
            profiles.Add(new SystemProfile("windows", "Windows", "原生桌面系统", "Windows Native", "可启动", "ready", "#59B7FF", true, ArtifactKind.WindowsExe));
            profiles.Add(new SystemProfile("android", "Android", "APK 虚拟设备", adb ? "ADB device bridge" : "Android VM backend", adb ? "已发现 ADB" : "需要引擎", adb ? "ready" : "missing", "#72E08B", adb, ArtifactKind.AndroidApk));
            profiles.Add(new SystemProfile("ios", "iOS", "IPA 兼容运行层", "ARM64 HLE", "实验可启动", "experimental", "#A993FF", true, ArtifactKind.AppleIpa));
            profiles.Add(new SystemProfile("windowsphone", "Windows Phone", "遗产应用系统", "WP VM backend", "需要引擎", "missing", "#46D6CE", false, ArtifactKind.Unknown));
            return profiles;
        }
    }

    public enum ArtifactKind
    {
        Unknown,
        WindowsExe,
        AndroidApk,
        AppleIpa
    }

    public enum ExecutionRoute
    {
        Reject,
        InspectOnly,
        Native,
        VirtualMachine,
        Translation
    }

    public sealed class MetadataItem
    {
        public string Name { get; set; }
        public string Value { get; set; }

        public MetadataItem(string name, string value)
        {
            Name = name;
            Value = value;
        }
    }

    public sealed class ArtifactInfo
    {
        public string Path { get; set; }
        public string Name { get; set; }
        public ArtifactKind Kind { get; set; }
        public string Format { get; set; }
        public string Architecture { get; set; }
        public string Target { get; set; }
        public string Identity { get; set; }
        public string Sha256 { get; set; }
        public long Size { get; set; }
        public ExecutionRoute Route { get; set; }
        public string Status { get; set; }
        public string StatusTone { get; set; }
        public string Summary { get; set; }
        public bool BuiltIn { get; set; }
        public bool Encrypted { get; set; }
        public bool CanRun { get; set; }
        public List<MetadataItem> Metadata { get; private set; }
        public Dictionary<string, string> Tags { get; private set; }

        public ArtifactInfo()
        {
            Metadata = new List<MetadataItem>();
            Tags = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            Name = "Unknown package";
            Format = "Unknown";
            Architecture = "Unknown";
            Target = "Unknown";
            Identity = "—";
            Status = "UNSUPPORTED";
            StatusTone = "blocked";
            Summary = "No compatible adapter found.";
            Route = ExecutionRoute.Reject;
        }

        public string KindLabel
        {
            get
            {
                if (Kind == ArtifactKind.WindowsExe) return "EXE";
                if (Kind == ArtifactKind.AndroidApk) return "APK";
                if (Kind == ArtifactKind.AppleIpa) return "IPA";
                return "?";
            }
        }
    }

    public sealed class ExecutionTrace
    {
        public string Lane { get; set; }
        public string Address { get; set; }
        public string Instruction { get; set; }
        public string Effect { get; set; }
    }

    public sealed class ExecutionResult
    {
        public bool Success { get; set; }
        public string Title { get; set; }
        public string Message { get; set; }
        public string Output { get; set; }
        public List<ExecutionTrace> Trace { get; private set; }

        public ExecutionResult()
        {
            Title = "Stopped";
            Message = "No execution result.";
            Output = String.Empty;
            Trace = new List<ExecutionTrace>();
        }
    }

    public interface IArtifactAdapter
    {
        ArtifactKind Kind { get; }
        bool Probe(string path);
        ArtifactInfo Inspect(string path, bool builtIn);
        ExecutionResult Run(ArtifactInfo artifact, string action);
    }

    public static class RuntimeUtil
    {
        public static string ComputeSha256(string path)
        {
            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (SHA256 hash = SHA256.Create())
            {
                byte[] digest = hash.ComputeHash(stream);
                StringBuilder builder = new StringBuilder(digest.Length * 2);
                for (int index = 0; index < digest.Length; index++)
                    builder.Append(digest[index].ToString("x2", CultureInfo.InvariantCulture));
                return builder.ToString();
            }
        }

        public static string FormatBytes(long bytes)
        {
            string[] units = { "B", "KB", "MB", "GB" };
            double value = bytes;
            int unit = 0;
            while (value >= 1024.0 && unit < units.Length - 1)
            {
                value /= 1024.0;
                unit++;
            }
            return value.ToString(unit == 0 ? "0" : "0.0", CultureInfo.InvariantCulture) + " " + units[unit];
        }

        public static string FindExecutable(string fileName)
        {
            string path = Environment.GetEnvironmentVariable("PATH") ?? String.Empty;
            string[] directories = path.Split(new[] { System.IO.Path.PathSeparator }, StringSplitOptions.RemoveEmptyEntries);
            for (int index = 0; index < directories.Length; index++)
            {
                try
                {
                    string candidate = System.IO.Path.Combine(directories[index].Trim(), fileName);
                    if (File.Exists(candidate)) return candidate;
                }
                catch { }
            }
            return null;
        }

        public static string FindAndroidAdb()
        {
            string path = FindExecutable("adb.exe");
            if (path != null) return path;
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string candidate = System.IO.Path.Combine(local, "Android", "Sdk", "platform-tools", "adb.exe");
            return File.Exists(candidate) ? candidate : null;
        }

        public static bool HasAdbDevice(string adbPath)
        {
            if (String.IsNullOrWhiteSpace(adbPath) || !File.Exists(adbPath)) return false;
            try
            {
                int exit;
                string devices = RunAndCapture(adbPath, "devices", 4000, out exit);
                if (exit != 0) return false;
                string[] lines = devices.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
                for (int index = 0; index < lines.Length; index++)
                    if (lines[index].Contains("\tdevice")) return true;
            }
            catch { }
            return false;
        }

        public static string RunAndCapture(string fileName, string arguments, int timeoutMilliseconds, out int exitCode)
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = fileName;
            start.Arguments = arguments;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            using (Process process = Process.Start(start))
            {
                string stdout = process.StandardOutput.ReadToEnd();
                string stderr = process.StandardError.ReadToEnd();
                if (!process.WaitForExit(timeoutMilliseconds))
                {
                    try { process.Kill(); } catch { }
                    exitCode = -1;
                    return "Process timed out.";
                }
                exitCode = process.ExitCode;
                return (stdout + (String.IsNullOrWhiteSpace(stderr) ? String.Empty : Environment.NewLine + stderr)).Trim();
            }
        }
    }
}
