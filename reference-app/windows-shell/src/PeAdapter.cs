using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;

namespace JidanOS
{
    public sealed class PeAdapter : IArtifactAdapter
    {
        public ArtifactKind Kind { get { return ArtifactKind.WindowsExe; } }

        public bool Probe(string path)
        {
            try
            {
                using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    if (stream.Length < 64) return false;
                    return stream.ReadByte() == 'M' && stream.ReadByte() == 'Z';
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
            artifact.Kind = ArtifactKind.WindowsExe;
            artifact.Format = "PE/COFF";
            artifact.Target = "Windows";
            artifact.Size = file.Length;
            artifact.BuiltIn = builtIn;
            artifact.Sha256 = RuntimeUtil.ComputeSha256(path);

            using (FileStream stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            using (BinaryReader reader = new BinaryReader(stream))
            {
                if (reader.ReadUInt16() != 0x5A4D) throw new InvalidDataException("Invalid DOS MZ header.");
                stream.Position = 0x3C;
                int peOffset = reader.ReadInt32();
                if (peOffset < 64 || peOffset > stream.Length - 24) throw new InvalidDataException("Invalid PE header offset.");
                stream.Position = peOffset;
                if (reader.ReadUInt32() != 0x00004550) throw new InvalidDataException("Missing PE signature.");

                ushort machine = reader.ReadUInt16();
                ushort sections = reader.ReadUInt16();
                uint timestamp = reader.ReadUInt32();
                reader.ReadUInt32();
                reader.ReadUInt32();
                ushort optionalSize = reader.ReadUInt16();
                ushort characteristics = reader.ReadUInt16();
                long optionalOffset = stream.Position;
                if (optionalSize < 70 || optionalOffset + optionalSize > stream.Length)
                    throw new InvalidDataException("Invalid PE optional header.");

                ushort magic = reader.ReadUInt16();
                bool pe64 = magic == 0x20B;
                if (!pe64 && magic != 0x10B) throw new InvalidDataException("Unsupported PE optional header.");
                stream.Position = optionalOffset + 16;
                uint entryPoint = reader.ReadUInt32();
                ulong imageBase;
                if (pe64)
                {
                    stream.Position = optionalOffset + 24;
                    imageBase = reader.ReadUInt64();
                }
                else
                {
                    stream.Position = optionalOffset + 28;
                    imageBase = reader.ReadUInt32();
                }
                stream.Position = optionalOffset + 68;
                ushort subsystem = reader.ReadUInt16();

                int dataDirectoryOffset = pe64 ? 112 : 96;
                bool signed = false;
                if (optionalSize >= dataDirectoryOffset + 40)
                {
                    stream.Position = optionalOffset + dataDirectoryOffset + (8 * 4);
                    uint certOffset = reader.ReadUInt32();
                    uint certSize = reader.ReadUInt32();
                    signed = certOffset > 0 && certSize > 0 && certOffset + certSize <= stream.Length;
                }

                artifact.Architecture = MachineName(machine);
                artifact.Identity = artifact.Name;
                artifact.Route = IsNativeMachine(machine) ? ExecutionRoute.Native : ExecutionRoute.InspectOnly;
                artifact.CanRun = IsNativeMachine(machine);
                artifact.Status = artifact.CanRun ? "可运行" : "架构不匹配";
                artifact.StatusTone = artifact.CanRun ? "ready" : "missing";
                artifact.Summary = artifact.CanRun
                    ? "由 Windows 原生进程加载器执行。"
                    : "这个 PE 架构不能在当前 x64 Windows 宿主直接运行。";

                artifact.Metadata.Add(new MetadataItem("ROUTE", artifact.Route.ToString().ToUpperInvariant()));
                artifact.Metadata.Add(new MetadataItem("MACHINE", "0x" + machine.ToString("x4") + " · " + artifact.Architecture));
                artifact.Metadata.Add(new MetadataItem("ENTRY RVA", "0x" + entryPoint.ToString("x8")));
                artifact.Metadata.Add(new MetadataItem("IMAGE BASE", "0x" + imageBase.ToString("x")));
                artifact.Metadata.Add(new MetadataItem("SECTIONS", sections.ToString(CultureInfo.InvariantCulture)));
                artifact.Metadata.Add(new MetadataItem("SUBSYSTEM", SubsystemName(subsystem)));
                artifact.Metadata.Add(new MetadataItem("SIGNATURE", signed ? "Authenticode table present" : "No certificate table"));
                artifact.Metadata.Add(new MetadataItem("CHARACTERISTICS", "0x" + characteristics.ToString("x4")));
                if (timestamp != 0)
                {
                    try
                    {
                        DateTime date = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(timestamp);
                        artifact.Metadata.Add(new MetadataItem("LINK TIME", date.ToString("u")));
                    }
                    catch { }
                }
            }

            artifact.Metadata.Add(new MetadataItem("SIZE", RuntimeUtil.FormatBytes(file.Length)));
            artifact.Metadata.Add(new MetadataItem("SHA-256", artifact.Sha256));
            return artifact;
        }

        public ExecutionResult Run(ArtifactInfo artifact, string action)
        {
            ExecutionResult result = new ExecutionResult();
            if (!artifact.CanRun)
            {
                result.Title = "Architecture mismatch";
                result.Message = artifact.Summary;
                return result;
            }

            try
            {
                if (artifact.BuiltIn)
                {
                    ProcessStartInfo start = new ProcessStartInfo();
                    start.FileName = artifact.Path;
                    start.Arguments = "--self-test";
                    start.UseShellExecute = false;
                    start.CreateNoWindow = true;
                    using (Process process = Process.Start(start))
                    {
                        int pid = process.Id;
                        if (!process.WaitForExit(5000))
                        {
                            try { process.Kill(); } catch { }
                            result.Title = "Native process timed out";
                            result.Message = "The built-in native probe did not exit in time.";
                            return result;
                        }
                        result.Success = process.ExitCode == 27;
                        result.Title = result.Success ? "Windows native process running" : "Native probe failed";
                        result.Message = result.Success
                            ? "Windows created a real child process and the package returned the expected result."
                            : "The native child process returned an unexpected exit code.";
                        result.Output = "PID " + pid + Environment.NewLine + "Route NATIVE" + Environment.NewLine + "Exit code " + process.ExitCode;
                        result.Trace.Add(new ExecutionTrace { Lane = "N", Address = "PID " + pid, Instruction = "CreateProcess", Effect = "Windows loader accepted PE" });
                        result.Trace.Add(new ExecutionTrace { Lane = "N", Address = "EXIT", Instruction = "--self-test", Effect = "code " + process.ExitCode });
                        return result;
                    }
                }

                ProcessStartInfo external = new ProcessStartInfo();
                external.FileName = artifact.Path;
                external.WorkingDirectory = System.IO.Path.GetDirectoryName(artifact.Path);
                external.UseShellExecute = true;
                Process launched = Process.Start(external);
                result.Success = true;
                result.Title = "Windows process started";
                result.Message = "The package is now running as a normal Windows process.";
                result.Output = "PID " + launched.Id + Environment.NewLine + "Route NATIVE";
                result.Trace.Add(new ExecutionTrace { Lane = "N", Address = "PID " + launched.Id, Instruction = "ShellExecute", Effect = "process created" });
                return result;
            }
            catch (Exception error)
            {
                result.Title = "Windows could not start the package";
                result.Message = error.Message;
                result.Output = error.ToString();
                return result;
            }
        }

        private static bool IsNativeMachine(ushort machine)
        {
            return machine == 0x8664 || machine == 0x014C;
        }

        private static string MachineName(ushort machine)
        {
            if (machine == 0x8664) return "x64";
            if (machine == 0x014C) return "x86";
            if (machine == 0xAA64) return "ARM64";
            if (machine == 0x01C4) return "ARMv7";
            return "machine-0x" + machine.ToString("x4");
        }

        private static string SubsystemName(ushort subsystem)
        {
            if (subsystem == 2) return "Windows GUI";
            if (subsystem == 3) return "Windows Console";
            if (subsystem == 10) return "EFI application";
            return "subsystem-" + subsystem;
        }
    }
}
