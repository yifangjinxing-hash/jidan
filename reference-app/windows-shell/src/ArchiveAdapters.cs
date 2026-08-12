using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Xml.Linq;

namespace JidanOS
{
    internal static class ArchiveSafety
    {
        public static void Validate(ZipArchive archive)
        {
            if (archive.Entries.Count > 100000) throw new InvalidDataException("Archive contains too many entries.");
            long total = 0;
            for (int index = 0; index < archive.Entries.Count; index++)
            {
                ZipArchiveEntry entry = archive.Entries[index];
                string normalized = entry.FullName.Replace('\\', '/');
                if (normalized.StartsWith("/", StringComparison.Ordinal) || normalized.Contains("../"))
                    throw new InvalidDataException("Archive contains an unsafe path: " + entry.FullName);
                total += entry.Length;
                if (total > 16L * 1024L * 1024L * 1024L)
                    throw new InvalidDataException("Archive expands beyond the 16 GB inspection limit.");
                if (entry.Length > 256L * 1024L * 1024L && entry.CompressedLength > 0 && entry.Length / entry.CompressedLength > 500)
                    throw new InvalidDataException("Archive contains a suspicious compression ratio.");
            }
        }

        public static byte[] ReadEntry(ZipArchiveEntry entry, long maximumBytes)
        {
            if (entry == null) throw new InvalidDataException("Required package entry is missing.");
            if (entry.Length > maximumBytes) throw new InvalidDataException("Package entry is too large: " + entry.FullName);
            using (Stream input = entry.Open())
            using (MemoryStream output = new MemoryStream())
            {
                input.CopyTo(output);
                return output.ToArray();
            }
        }
    }

    public sealed class ApkAdapter : IArtifactAdapter
    {
        public ArtifactKind Kind { get { return ArtifactKind.AndroidApk; } }

        public bool Probe(string path)
        {
            try
            {
                using (ZipArchive archive = ZipFile.OpenRead(path))
                {
                    bool manifest = false;
                    bool dex = false;
                    int limit = Math.Min(archive.Entries.Count, 20000);
                    for (int index = 0; index < limit; index++)
                    {
                        string name = archive.Entries[index].FullName.Replace('\\', '/');
                        if (String.Equals(name, "AndroidManifest.xml", StringComparison.OrdinalIgnoreCase)) manifest = true;
                        if (name.StartsWith("classes", StringComparison.OrdinalIgnoreCase) && name.EndsWith(".dex", StringComparison.OrdinalIgnoreCase)) dex = true;
                    }
                    return manifest && dex;
                }
            }
            catch { return false; }
        }

        public ArtifactInfo Inspect(string path, bool builtIn)
        {
            FileInfo file = new FileInfo(path);
            ArtifactInfo artifact = new ArtifactInfo();
            artifact.Path = path;
            artifact.Name = file.Name;
            artifact.Kind = ArtifactKind.AndroidApk;
            artifact.Format = "APK / ZIP";
            artifact.Target = "Android";
            artifact.Size = file.Length;
            artifact.BuiltIn = builtIn;
            artifact.Sha256 = RuntimeUtil.ComputeSha256(path);

            HashSet<string> abis = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            int dexCount = 0;
            bool signed = false;
            bool binaryManifest = true;
            string packageName = "Unknown Android package";
            string minSdk = "—";
            string targetSdk = "—";
            long expanded = 0;

            using (ZipArchive archive = ZipFile.OpenRead(path))
            {
                ArchiveSafety.Validate(archive);
                ZipArchiveEntry manifestEntry = null;
                for (int index = 0; index < archive.Entries.Count; index++)
                {
                    ZipArchiveEntry entry = archive.Entries[index];
                    string name = entry.FullName.Replace('\\', '/');
                    expanded += entry.Length;
                    if (String.Equals(name, "AndroidManifest.xml", StringComparison.OrdinalIgnoreCase)) manifestEntry = entry;
                    if (name.StartsWith("classes", StringComparison.OrdinalIgnoreCase) && name.EndsWith(".dex", StringComparison.OrdinalIgnoreCase)) dexCount++;
                    if (name.StartsWith("lib/", StringComparison.OrdinalIgnoreCase))
                    {
                        string[] parts = name.Split('/');
                        if (parts.Length >= 3 && parts[2].EndsWith(".so", StringComparison.OrdinalIgnoreCase)) abis.Add(parts[1]);
                    }
                    if (name.StartsWith("META-INF/", StringComparison.OrdinalIgnoreCase) &&
                        (name.EndsWith(".RSA", StringComparison.OrdinalIgnoreCase) || name.EndsWith(".DSA", StringComparison.OrdinalIgnoreCase) || name.EndsWith(".EC", StringComparison.OrdinalIgnoreCase)))
                        signed = true;
                }

                if (manifestEntry != null && manifestEntry.Length <= 2 * 1024 * 1024)
                {
                    byte[] manifestBytes = ArchiveSafety.ReadEntry(manifestEntry, 2 * 1024 * 1024);
                    string text = Encoding.UTF8.GetString(manifestBytes).TrimStart('\uFEFF', ' ', '\t', '\r', '\n');
                    if (text.StartsWith("<", StringComparison.Ordinal))
                    {
                        binaryManifest = false;
                        try
                        {
                            XDocument document = XDocument.Parse(text);
                            XElement root = document.Root;
                            if (root != null)
                            {
                                XAttribute package = root.Attribute("package");
                                if (package != null) packageName = package.Value;
                                XNamespace android = "http://schemas.android.com/apk/res/android";
                                XElement sdk = root.Elements().FirstOrDefault(element => element.Name.LocalName == "uses-sdk");
                                if (sdk != null)
                                {
                                    XAttribute minimum = sdk.Attribute(android + "minSdkVersion");
                                    XAttribute target = sdk.Attribute(android + "targetSdkVersion");
                                    if (minimum != null) minSdk = minimum.Value;
                                    if (target != null) targetSdk = target.Value;
                                }
                            }
                        }
                        catch { }
                    }
                }

                artifact.Metadata.Add(new MetadataItem("ENTRIES", archive.Entries.Count.ToString(CultureInfo.InvariantCulture)));
            }

            if (builtIn && packageName == "Unknown Android package" && String.Equals(file.Name, "JidanDemo.apk", StringComparison.OrdinalIgnoreCase))
                packageName = "org.jidan.demo";
            string adb = RuntimeUtil.FindAndroidAdb();
            bool device = RuntimeUtil.HasAdbDevice(adb);

            artifact.Identity = packageName;
            artifact.Architecture = abis.Count == 0 ? "DEX / any" : String.Join(", ", abis.ToArray());
            artifact.Route = device ? ExecutionRoute.VirtualMachine : ExecutionRoute.InspectOnly;
            artifact.CanRun = device;
            artifact.Status = device ? "可运行" : "需要 Android 引擎";
            artifact.StatusTone = device ? "ready" : "missing";
            artifact.Summary = device
                ? "已发现 ADB 设备；可以安装并启动这个 APK。"
                : "包已识别，但本机没有正在运行的 Android 虚拟设备。";
            artifact.Tags["adb"] = adb ?? String.Empty;
            artifact.Tags["package"] = packageName == "Unknown Android package" ? String.Empty : packageName;
            artifact.Metadata.Add(new MetadataItem("ROUTE", artifact.Route.ToString().ToUpperInvariant()));
            artifact.Metadata.Add(new MetadataItem("PACKAGE", packageName));
            artifact.Metadata.Add(new MetadataItem("MANIFEST", binaryManifest ? "Binary AXML" : "Readable XML"));
            artifact.Metadata.Add(new MetadataItem("SDK", "min " + minSdk + " · target " + targetSdk));
            artifact.Metadata.Add(new MetadataItem("DEX", dexCount.ToString(CultureInfo.InvariantCulture) + " file(s)"));
            artifact.Metadata.Add(new MetadataItem("NATIVE ABI", artifact.Architecture));
            artifact.Metadata.Add(new MetadataItem("SIGNATURE", signed ? "Signing block/certificate metadata present" : "No META-INF certificate"));
            artifact.Metadata.Add(new MetadataItem("EXPANDED", RuntimeUtil.FormatBytes(expanded)));
            artifact.Metadata.Add(new MetadataItem("SIZE", RuntimeUtil.FormatBytes(file.Length)));
            artifact.Metadata.Add(new MetadataItem("SHA-256", artifact.Sha256));
            return artifact;
        }

        public ExecutionResult Run(ArtifactInfo artifact, string action)
        {
            ExecutionResult result = new ExecutionResult();
            string adb = artifact.Tags.ContainsKey("adb") ? artifact.Tags["adb"] : null;
            if (!artifact.CanRun || String.IsNullOrWhiteSpace(adb))
            {
                result.Title = "Android engine required";
                result.Message = "Start an Android virtual device with ADB, then refresh the package.";
                result.Output = "未执行：没有 Android guest session。";
                result.Trace.Add(new ExecutionTrace { Lane = "D", Address = "APK", Instruction = "route", Effect = "Android VM backend missing" });
                return result;
            }

            try
            {
                int exit;
                string install = RuntimeUtil.RunAndCapture(adb, "install -r \"" + artifact.Path.Replace("\"", "\\\"") + "\"", 120000, out exit);
                result.Output = install;
                if (exit != 0 || install.IndexOf("Success", StringComparison.OrdinalIgnoreCase) < 0)
                {
                    result.Title = "APK install failed";
                    result.Message = "The Android guest rejected the package.";
                    result.Trace.Add(new ExecutionTrace { Lane = "D", Address = "ADB", Instruction = "install -r", Effect = "exit " + exit });
                    return result;
                }
                string packageName = artifact.Tags.ContainsKey("package") ? artifact.Tags["package"] : String.Empty;
                if (!String.IsNullOrWhiteSpace(packageName))
                {
                    int launchExit;
                    string launch = RuntimeUtil.RunAndCapture(adb, "shell monkey -p \"" + packageName + "\" -c android.intent.category.LAUNCHER 1", 15000, out launchExit);
                    result.Output += Environment.NewLine + launch;
                }
                result.Success = true;
                result.Title = "APK running in Android guest";
                result.Message = "ADB installed the package into a real Android guest session.";
                result.Trace.Add(new ExecutionTrace { Lane = "V", Address = "ADB", Instruction = "install -r", Effect = "Success" });
                result.Trace.Add(new ExecutionTrace { Lane = "V", Address = packageName, Instruction = "launch", Effect = "intent dispatched" });
                return result;
            }
            catch (Exception error)
            {
                result.Title = "Android execution failed";
                result.Message = error.Message;
                result.Output = error.ToString();
                return result;
            }
        }

    }

    public sealed class IpaAdapter : IArtifactAdapter
    {
        public ArtifactKind Kind { get { return ArtifactKind.AppleIpa; } }

        public bool Probe(string path)
        {
            try
            {
                using (ZipArchive archive = ZipFile.OpenRead(path))
                {
                    int limit = Math.Min(archive.Entries.Count, 20000);
                    for (int index = 0; index < limit; index++)
                    {
                        string name = archive.Entries[index].FullName.Replace('\\', '/');
                        if (name.StartsWith("Payload/", StringComparison.OrdinalIgnoreCase) && name.IndexOf(".app/", StringComparison.OrdinalIgnoreCase) > 0)
                            return true;
                    }
                    return false;
                }
            }
            catch { return false; }
        }

        public ArtifactInfo Inspect(string path, bool builtIn)
        {
            FileInfo file = new FileInfo(path);
            ArtifactInfo artifact = new ArtifactInfo();
            artifact.Path = path;
            artifact.Name = file.Name;
            artifact.Kind = ArtifactKind.AppleIpa;
            artifact.Format = "IPA / Mach-O 64";
            artifact.Target = "iOS";
            artifact.Size = file.Length;
            artifact.BuiltIn = builtIn;
            artifact.Sha256 = RuntimeUtil.ComputeSha256(path);

            string bundleName = file.Name;
            string bundleId = "Unknown iOS bundle";
            string executableName = null;
            string appPrefix = null;
            ZipArchiveEntry executableEntry = null;
            MachOInfo macho = null;
            int commandOffset = -1;

            using (ZipArchive archive = ZipFile.OpenRead(path))
            {
                ArchiveSafety.Validate(archive);
                ZipArchiveEntry plistEntry = archive.Entries.FirstOrDefault(entry =>
                {
                    string name = entry.FullName.Replace('\\', '/');
                    return name.StartsWith("Payload/", StringComparison.OrdinalIgnoreCase) && name.EndsWith(".app/Info.plist", StringComparison.OrdinalIgnoreCase);
                });
                if (plistEntry == null) throw new InvalidDataException("IPA has no Payload/*.app/Info.plist.");
                string plistPath = plistEntry.FullName.Replace('\\', '/');
                appPrefix = plistPath.Substring(0, plistPath.Length - "Info.plist".Length);
                string[] prefixParts = appPrefix.TrimEnd('/').Split('/');
                bundleName = prefixParts[prefixParts.Length - 1].Replace(".app", String.Empty);
                byte[] plistBytes = ArchiveSafety.ReadEntry(plistEntry, 8 * 1024 * 1024);
                string plistText = Encoding.UTF8.GetString(plistBytes).TrimStart('\uFEFF', ' ', '\t', '\r', '\n');
                if (plistText.StartsWith("<", StringComparison.Ordinal))
                {
                    Dictionary<string, string> plist = ParsePlist(plistText);
                    if (plist.ContainsKey("CFBundleExecutable")) executableName = plist["CFBundleExecutable"];
                    if (plist.ContainsKey("CFBundleIdentifier")) bundleId = plist["CFBundleIdentifier"];
                    if (plist.ContainsKey("CFBundleDisplayName")) bundleName = plist["CFBundleDisplayName"];
                }
                if (String.IsNullOrWhiteSpace(executableName)) executableName = prefixParts[prefixParts.Length - 1].Replace(".app", String.Empty);
                string executablePath = appPrefix + executableName;
                executableEntry = archive.Entries.FirstOrDefault(entry => String.Equals(entry.FullName.Replace('\\', '/'), executablePath, StringComparison.Ordinal));
                if (executableEntry == null) throw new InvalidDataException("IPA executable was not found: " + executablePath);
                byte[] binary = ArchiveSafety.ReadEntry(executableEntry, 512L * 1024L * 1024L);
                macho = MachOParser.Parse(binary);

                ZipArchiveEntry runtimeEntry = archive.Entries.FirstOrDefault(entry => String.Equals(entry.FullName.Replace('\\', '/'), appPrefix + "JidanRuntime.ini", StringComparison.OrdinalIgnoreCase));
                if (runtimeEntry != null && runtimeEntry.Length < 4096)
                {
                    string runtimeText = Encoding.UTF8.GetString(ArchiveSafety.ReadEntry(runtimeEntry, 4096));
                    string[] lines = runtimeText.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
                    for (int index = 0; index < lines.Length; index++)
                    {
                        if (lines[index].StartsWith("commandOffset=", StringComparison.OrdinalIgnoreCase))
                            Int32.TryParse(lines[index].Substring("commandOffset=".Length), NumberStyles.Integer, CultureInfo.InvariantCulture, out commandOffset);
                    }
                }
                artifact.Metadata.Add(new MetadataItem("ENTRIES", archive.Entries.Count.ToString(CultureInfo.InvariantCulture)));
            }

            artifact.Name = bundleName;
            artifact.Identity = bundleId;
            artifact.Architecture = macho.Architecture;
            artifact.Encrypted = macho.CryptId != 0;
            artifact.Route = artifact.Encrypted ? ExecutionRoute.Reject : ExecutionRoute.Translation;
            artifact.CanRun = !artifact.Encrypted && macho.TextSize > 0 && macho.Architecture == "arm64";
            artifact.Status = artifact.Encrypted ? "FairPlay 加密" : (artifact.CanRun ? "实验可运行" : "暂不可运行");
            artifact.StatusTone = artifact.Encrypted ? "blocked" : (artifact.CanRun ? "experimental" : "missing");
            artifact.Summary = artifact.Encrypted
                ? "cryptid 非零；本运行器不会解密或绕过 FairPlay。"
                : (artifact.CanRun ? "未加密 ARM64 guest 可进入 clean-room HLE。" : "包可读取，但当前翻译器不支持这个入口。 ");
            artifact.Tags["appPrefix"] = appPrefix;
            artifact.Tags["executable"] = executableName;
            artifact.Tags["commandOffset"] = commandOffset.ToString(CultureInfo.InvariantCulture);
            artifact.Metadata.Add(new MetadataItem("ROUTE", artifact.Route.ToString().ToUpperInvariant()));
            artifact.Metadata.Add(new MetadataItem("BUNDLE", bundleId));
            artifact.Metadata.Add(new MetadataItem("EXECUTABLE", executableName));
            artifact.Metadata.Add(new MetadataItem("ARCH", macho.Architecture));
            artifact.Metadata.Add(new MetadataItem("BUILD", macho.Platform + " min " + macho.MinOS + " · SDK " + macho.Sdk));
            artifact.Metadata.Add(new MetadataItem("ENTRY", "file+0x" + macho.EntryFileOffset.ToString("x")));
            artifact.Metadata.Add(new MetadataItem("ENCRYPTION", macho.CryptId == 0 ? "cryptid=0 · readable" : "cryptid=" + macho.CryptId + " · blocked"));
            artifact.Metadata.Add(new MetadataItem("CODE SIGNATURE", macho.HasCodeSignature ? "load command present" : "not present"));
            artifact.Metadata.Add(new MetadataItem("SIZE", RuntimeUtil.FormatBytes(file.Length)));
            artifact.Metadata.Add(new MetadataItem("SHA-256", artifact.Sha256));
            return artifact;
        }

        public ExecutionResult Run(ArtifactInfo artifact, string action)
        {
            if (!artifact.CanRun)
            {
                ExecutionResult blocked = new ExecutionResult();
                blocked.Title = artifact.Encrypted ? "Encrypted IPA blocked" : "Missing iOS runtime capability";
                blocked.Message = artifact.Summary;
                blocked.Output = "未执行：没有建立 guest session。";
                blocked.Trace.Add(new ExecutionTrace { Lane = "D", Address = "IPA", Instruction = "route", Effect = artifact.Status });
                return blocked;
            }

            try
            {
                using (ZipArchive archive = ZipFile.OpenRead(artifact.Path))
                {
                    string appPrefix = artifact.Tags["appPrefix"];
                    string executableName = artifact.Tags["executable"];
                    ZipArchiveEntry executable = archive.Entries.First(entry => String.Equals(entry.FullName.Replace('\\', '/'), appPrefix + executableName, StringComparison.Ordinal));
                    byte[] binary = ArchiveSafety.ReadEntry(executable, 512L * 1024L * 1024L);
                    MachOInfo macho = MachOParser.Parse(binary);
                    int commandOffset = -1;
                    if (artifact.Tags.ContainsKey("commandOffset")) Int32.TryParse(artifact.Tags["commandOffset"], out commandOffset);
                    return Arm64Hle.Execute(binary, macho, action, commandOffset);
                }
            }
            catch (Exception error)
            {
                ExecutionResult failed = new ExecutionResult();
                failed.Title = "iOS HLE stopped";
                failed.Message = error.Message;
                failed.Output = error.ToString();
                return failed;
            }
        }

        private static Dictionary<string, string> ParsePlist(string xml)
        {
            Dictionary<string, string> values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                XDocument document = XDocument.Parse(xml);
                XElement dict = document.Descendants().FirstOrDefault(element => element.Name.LocalName == "dict");
                if (dict == null) return values;
                List<XElement> children = dict.Elements().ToList();
                for (int index = 0; index + 1 < children.Count; index++)
                {
                    if (children[index].Name.LocalName != "key") continue;
                    string key = children[index].Value;
                    XElement value = children[index + 1];
                    if (value.Name.LocalName == "string" || value.Name.LocalName == "integer") values[key] = value.Value;
                    index++;
                }
            }
            catch { }
            return values;
        }
    }
}
