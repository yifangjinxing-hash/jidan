using System;
using System.IO;
using System.Text;

namespace JidanOS
{
    public sealed class MachOInfo
    {
        public string Architecture { get; set; }
        public string Platform { get; set; }
        public string MinOS { get; set; }
        public string Sdk { get; set; }
        public long EntryFileOffset { get; set; }
        public int TextOffset { get; set; }
        public int TextSize { get; set; }
        public ulong TextAddress { get; set; }
        public int EntryOffsetInText { get; set; }
        public uint CryptId { get; set; }
        public bool HasCodeSignature { get; set; }
    }

    public static class MachOParser
    {
        private const uint MH_MAGIC_64 = 0xFEEDFACF;
        private const uint CPU_TYPE_ARM64 = 0x0100000C;
        private const uint LC_SEGMENT_64 = 0x19;
        private const uint LC_BUILD_VERSION = 0x32;
        private const uint LC_MAIN = 0x80000028;
        private const uint LC_ENCRYPTION_INFO_64 = 0x2C;
        private const uint LC_CODE_SIGNATURE = 0x1D;

        public static MachOInfo Parse(byte[] data)
        {
            Ensure(data, 0, 32, "Mach-O header");
            if (ReadU32(data, 0) != MH_MAGIC_64) throw new InvalidDataException("Only little-endian Mach-O 64 is supported.");
            uint cpu = ReadU32(data, 4);
            uint commands = ReadU32(data, 16);
            uint commandBytes = ReadU32(data, 20);
            if (cpu != CPU_TYPE_ARM64) throw new InvalidDataException("Only ARM64 Mach-O is supported by this HLE build.");
            Ensure(data, 32, checked((int)commandBytes), "Mach-O load commands");

            MachOInfo info = new MachOInfo();
            info.Architecture = "arm64";
            info.Platform = "iOS";
            info.MinOS = "—";
            info.Sdk = "—";
            info.EntryFileOffset = -1;
            info.TextOffset = -1;
            info.TextSize = 0;
            int cursor = 32;
            for (uint index = 0; index < commands; index++)
            {
                Ensure(data, cursor, 8, "load command");
                uint command = ReadU32(data, cursor);
                int size = checked((int)ReadU32(data, cursor + 4));
                if (size < 8) throw new InvalidDataException("Invalid Mach-O load command size.");
                Ensure(data, cursor, size, "load command");

                if (command == LC_SEGMENT_64)
                {
                    if (size < 72) throw new InvalidDataException("Truncated LC_SEGMENT_64.");
                    uint sectionCount = ReadU32(data, cursor + 64);
                    int sectionCursor = cursor + 72;
                    for (uint section = 0; section < sectionCount; section++)
                    {
                        Ensure(data, sectionCursor, 80, "Mach-O section");
                        string sectionName = ReadName(data, sectionCursor, 16);
                        string segmentName = ReadName(data, sectionCursor + 16, 16);
                        if (sectionName == "__text" && segmentName == "__TEXT")
                        {
                            ulong address = ReadU64(data, sectionCursor + 32);
                            ulong sectionSize = ReadU64(data, sectionCursor + 40);
                            uint offset = ReadU32(data, sectionCursor + 48);
                            if (sectionSize > Int32.MaxValue) throw new InvalidDataException("Mach-O text section is too large.");
                            Ensure(data, checked((int)offset), checked((int)sectionSize), "Mach-O __text");
                            info.TextAddress = address;
                            info.TextOffset = checked((int)offset);
                            info.TextSize = checked((int)sectionSize);
                        }
                        sectionCursor += 80;
                    }
                }
                else if (command == LC_BUILD_VERSION)
                {
                    if (size < 24) throw new InvalidDataException("Truncated LC_BUILD_VERSION.");
                    uint platform = ReadU32(data, cursor + 8);
                    info.Platform = PlatformName(platform);
                    info.MinOS = Version(ReadU32(data, cursor + 12));
                    info.Sdk = Version(ReadU32(data, cursor + 16));
                }
                else if (command == LC_MAIN)
                {
                    if (size < 24) throw new InvalidDataException("Truncated LC_MAIN.");
                    ulong entry = ReadU64(data, cursor + 8);
                    if (entry > Int64.MaxValue) throw new InvalidDataException("Mach-O entry offset is invalid.");
                    info.EntryFileOffset = (long)entry;
                }
                else if (command == LC_ENCRYPTION_INFO_64)
                {
                    if (size >= 24) info.CryptId = ReadU32(data, cursor + 16);
                }
                else if (command == LC_CODE_SIGNATURE)
                {
                    info.HasCodeSignature = true;
                }
                cursor += size;
            }

            if (info.TextOffset < 0) throw new InvalidDataException("Mach-O has no __TEXT,__text section.");
            if (info.EntryFileOffset < 0) throw new InvalidDataException("Mach-O has no LC_MAIN entry point.");
            long relative = info.EntryFileOffset - info.TextOffset;
            if (relative < 0 || relative >= info.TextSize) throw new InvalidDataException("Mach-O entry point is outside __text.");
            info.EntryOffsetInText = checked((int)relative);
            return info;
        }

        private static string PlatformName(uint platform)
        {
            if (platform == 2) return "iOS";
            if (platform == 7) return "iOS Simulator";
            if (platform == 1) return "macOS";
            return "platform-" + platform;
        }

        private static string Version(uint value)
        {
            return (value >> 16) + "." + ((value >> 8) & 0xFF) + "." + (value & 0xFF);
        }

        private static string ReadName(byte[] data, int offset, int length)
        {
            Ensure(data, offset, length, "Mach-O name");
            int count = 0;
            while (count < length && data[offset + count] != 0) count++;
            return Encoding.ASCII.GetString(data, offset, count);
        }

        private static uint ReadU32(byte[] data, int offset)
        {
            Ensure(data, offset, 4, "uint32");
            return BitConverter.ToUInt32(data, offset);
        }

        private static ulong ReadU64(byte[] data, int offset)
        {
            Ensure(data, offset, 8, "uint64");
            return BitConverter.ToUInt64(data, offset);
        }

        private static void Ensure(byte[] data, int offset, int length, string label)
        {
            if (offset < 0 || length < 0 || offset > data.Length - length)
                throw new InvalidDataException(label + " exceeds file bounds.");
        }
    }
}
