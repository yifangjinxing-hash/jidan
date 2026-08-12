using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;

namespace JidanOS
{
    public static class TestHarness
    {
        public static bool Run(string outputPath)
        {
            List<string> lines = new List<string>();
            int passed = 0;
            int failed = 0;
            Action<string, bool, string> check = delegate(string name, bool condition, string detail)
            {
                if (condition)
                {
                    passed++;
                    lines.Add("PASS " + name + " · " + detail);
                }
                else
                {
                    failed++;
                    lines.Add("FAIL " + name + " · " + detail);
                }
            };

            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory;
                string self = Assembly.GetExecutingAssembly().Location;
                string apkPath = Path.Combine(root, "samples", "JidanDemo.apk");
                string ipaPath = Path.Combine(root, "samples", "JidanDemo.ipa");
                PackageInspector inspector = new PackageInspector();

                ArtifactInfo exe = inspector.Inspect(self, true);
                check("PE magic detection", exe.Kind == ArtifactKind.WindowsExe, exe.Format);
                check("PE architecture", exe.Architecture == "x64", exe.Architecture);
                check("Native route", exe.Route == ExecutionRoute.Native && exe.CanRun, exe.Route.ToString());
                ExecutionResult native = inspector.Run(exe, "boot");
                check("Native process execution", native.Success && native.Output.Contains("Exit code 27"), native.Output.Replace(Environment.NewLine, " / "));

                ArtifactInfo apk = inspector.Inspect(apkPath, true);
                check("APK container detection", apk.Kind == ArtifactKind.AndroidApk, apk.Format);
                check("APK manifest identity", apk.Identity == "org.jidan.demo", apk.Identity);
                check("APK DEX metadata", ContainsMetadata(apk, "DEX", "1 file"), "classes.dex");

                ArtifactInfo ipa = inspector.Inspect(ipaPath, true);
                check("IPA container detection", ipa.Kind == ArtifactKind.AppleIpa, ipa.Format);
                check("IPA Mach-O architecture", ipa.Architecture == "arm64", ipa.Architecture);
                check("IPA iOS 27 marker", ContainsMetadata(ipa, "BUILD", "27.0.0"), "LC_BUILD_VERSION");
                check("IPA unencrypted", !ipa.Encrypted && ipa.CanRun, ipa.Status);
                ExecutionResult guest = inspector.Run(ipa, "boot");
                check("ARM64 guest execution", guest.Success && guest.Title.Contains("ready"), guest.Title);
                check("Guest host bridge trace", guest.Trace.Exists(trace => trace.Instruction == "hlt #2"), guest.Trace.Count + " trace events");
                ExecutionResult payment = inspector.Run(ipa, "payment");
                check("Payment policy", payment.Success && payment.Title == "Payment blocked", payment.Title);

                List<SystemProfile> systems = SystemCatalog.Detect();
                check("System deck", systems.Count == 5, systems.Count + " system profiles");
                check("Jidan boot slot", systems.Exists(system => system.Id == "jidan" && system.CanBoot), "Jidan ready");
            }
            catch (Exception error)
            {
                failed++;
                lines.Add("FAIL unhandled exception · " + error);
            }

            lines.Add(String.Empty);
            lines.Add("RESULT " + passed + " passed / " + failed + " failed");
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputPath)));
            File.WriteAllLines(outputPath, lines.ToArray(), Encoding.UTF8);
            return failed == 0;
        }

        public static string FormatArtifact(ArtifactInfo artifact)
        {
            StringBuilder builder = new StringBuilder();
            builder.AppendLine("NAME=" + artifact.Name);
            builder.AppendLine("KIND=" + artifact.Kind);
            builder.AppendLine("FORMAT=" + artifact.Format);
            builder.AppendLine("ARCH=" + artifact.Architecture);
            builder.AppendLine("TARGET=" + artifact.Target);
            builder.AppendLine("IDENTITY=" + artifact.Identity);
            builder.AppendLine("ROUTE=" + artifact.Route);
            builder.AppendLine("STATUS=" + artifact.Status);
            builder.AppendLine("CAN_RUN=" + artifact.CanRun);
            builder.AppendLine("SHA256=" + artifact.Sha256);
            for (int index = 0; index < artifact.Metadata.Count; index++)
                builder.AppendLine("META." + artifact.Metadata[index].Name + "=" + artifact.Metadata[index].Value);
            return builder.ToString();
        }

        private static bool ContainsMetadata(ArtifactInfo artifact, string name, string value)
        {
            return artifact.Metadata.Exists(item => String.Equals(item.Name, name, StringComparison.OrdinalIgnoreCase) && item.Value.IndexOf(value, StringComparison.OrdinalIgnoreCase) >= 0);
        }
    }
}
