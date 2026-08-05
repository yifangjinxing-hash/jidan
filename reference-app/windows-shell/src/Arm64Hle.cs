using System;
using System.Globalization;
using System.IO;

namespace JidanOS
{
    public static class Arm64Hle
    {
        public static ExecutionResult Execute(byte[] binary, MachOInfo macho, string action, int commandOffset)
        {
            ExecutionResult result = new ExecutionResult();
            ulong[] registers = new ulong[31];
            bool zero = false;
            bool halted = false;
            int pc;
            if (String.IsNullOrWhiteSpace(action) || action == "boot" || commandOffset < 0)
            {
                pc = macho.EntryOffsetInText;
                result.Title = "Starting iOS guest";
                result.Message = "Executing the Mach-O entry point.";
            }
            else
            {
                pc = commandOffset;
                if (action == "settings") registers[0] = 1;
                else if (action == "payment") registers[0] = 2;
                else if (action == "voice") registers[0] = 3;
                else registers[0] = 0;
            }

            int steps = 0;
            while (!halted && steps < 1024)
            {
                if (pc < 0 || pc + 4 > macho.TextSize || (pc & 3) != 0)
                    throw new InvalidDataException("ARM64 PC left __text at offset 0x" + pc.ToString("x"));
                int instructionOffset = macho.TextOffset + pc;
                uint word = BitConverter.ToUInt32(binary, instructionOffset);
                int oldPc = pc;
                pc += 4;
                steps++;
                string address = "0x" + (macho.TextAddress + (ulong)oldPc).ToString("x16");

                if ((word & 0xFF800000u) == 0xD2800000u)
                {
                    int rd = (int)(word & 0x1F);
                    ulong immediate = (word >> 5) & 0xFFFFu;
                    int shift = (int)((word >> 21) & 3u) * 16;
                    immediate <<= shift;
                    if (rd != 31) registers[rd] = immediate;
                    result.Trace.Add(new ExecutionTrace { Lane = "E", Address = address, Instruction = "movz x" + rd + ", #" + immediate, Effect = "x" + rd + "=0x" + immediate.ToString("x") });
                }
                else if ((word & 0xFF000000u) == 0x91000000u)
                {
                    int rd = (int)(word & 0x1F);
                    int rn = (int)((word >> 5) & 0x1F);
                    ulong immediate = (word >> 10) & 0xFFFu;
                    if (((word >> 22) & 1u) != 0) immediate <<= 12;
                    ulong left = rn == 31 ? 0 : registers[rn];
                    if (rd != 31) registers[rd] = left + immediate;
                    result.Trace.Add(new ExecutionTrace { Lane = "E", Address = address, Instruction = "add x" + rd + ", x" + rn + ", #" + immediate, Effect = "exact u64" });
                }
                else if ((word & 0xFF000000u) == 0xF1000000u)
                {
                    int rd = (int)(word & 0x1F);
                    int rn = (int)((word >> 5) & 0x1F);
                    ulong immediate = (word >> 10) & 0xFFFu;
                    if (((word >> 22) & 1u) != 0) immediate <<= 12;
                    ulong left = rn == 31 ? 0 : registers[rn];
                    ulong value = unchecked(left - immediate);
                    zero = value == 0;
                    if (rd != 31) registers[rd] = value;
                    result.Trace.Add(new ExecutionTrace { Lane = "E", Address = address, Instruction = rd == 31 ? "cmp x" + rn + ", #" + immediate : "subs x" + rd, Effect = "Z=" + zero.ToString().ToLowerInvariant() });
                }
                else if ((word & 0xFF000010u) == 0x54000000u)
                {
                    int immediate = (int)((word >> 5) & 0x7FFFFu);
                    if ((immediate & 0x40000) != 0) immediate -= 0x80000;
                    int condition = (int)(word & 0xF);
                    bool taken;
                    if (condition == 0) taken = zero;
                    else if (condition == 1) taken = !zero;
                    else if (condition == 14) taken = true;
                    else
                    {
                        result.Trace.Add(new ExecutionTrace { Lane = "D", Address = address, Instruction = "b.cond", Effect = "condition not implemented" });
                        result.Title = "Missing ARM64 condition";
                        result.Message = "The bit-exact backend does not implement condition " + condition + ".";
                        result.Output = "Stopped after " + steps + " guest instructions.";
                        return result;
                    }
                    if (taken) pc = oldPc + immediate * 4;
                    result.Trace.Add(new ExecutionTrace { Lane = "E", Address = address, Instruction = condition == 0 ? "b.eq" : "b.ne", Effect = taken ? "taken -> 0x" + pc.ToString("x") : "not taken" });
                }
                else if ((word & 0xFFE0001Fu) == 0xD4400000u)
                {
                    int call = (int)((word >> 5) & 0xFFFFu);
                    string effect = HandleHostCall(call, registers[0], result);
                    result.Trace.Add(new ExecutionTrace { Lane = call == 15 ? "D" : "H", Address = address, Instruction = "hlt #" + call, Effect = effect });
                }
                else if (word == 0xD65F03C0u)
                {
                    halted = true;
                    result.Trace.Add(new ExecutionTrace { Lane = "E", Address = address, Instruction = "ret", Effect = "guest returned" });
                }
                else
                {
                    result.Trace.Add(new ExecutionTrace { Lane = "D", Address = address, Instruction = ".word 0x" + word.ToString("x8"), Effect = "unsupported instruction" });
                    result.Title = "Missing ARM64 instruction";
                    result.Message = "The guest reached an instruction that this HLE build has not implemented.";
                    result.Output = "Stopped at " + address + Environment.NewLine + "word 0x" + word.ToString("x8") + Environment.NewLine + "instructions " + steps;
                    return result;
                }
            }

            result.Success = halted;
            if (halted)
            {
                if (String.IsNullOrWhiteSpace(result.Title) || result.Title == "Starting iOS guest") result.Title = "iOS guest returned";
                if (String.IsNullOrWhiteSpace(result.Message) || result.Message == "Executing the Mach-O entry point.") result.Message = "The ARM64 Mach-O completed through the clean-room HLE.";
                result.Output = "Route TRANSLATION" + Environment.NewLine + "Guest instructions " + steps + Environment.NewLine + "Entry 0x" + macho.TextAddress.ToString("x16");
            }
            else
            {
                result.Title = "Guest step limit reached";
                result.Message = "Execution stopped after 1024 instructions.";
                result.Output = "Step limit reached.";
            }
            return result;
        }

        private static string HandleHostCall(int call, ulong argument, ExecutionResult result)
        {
            if (call == 1)
            {
                result.Title = "iOS " + argument + " ABI loaded";
                result.Message = "The guest confirmed its build target.";
                return "target ABI iOS " + argument;
            }
            if (call == 2)
            {
                if (argument == 1) return "ARM64 translation online";
                if (argument == 2) return "framework bridge online";
                if (argument == 3)
                {
                    result.Title = "iOS guest ready";
                    result.Message = "The clean-room ARM64 guest is ready for commands.";
                    return "guest ready";
                }
                return "boot stage " + argument;
            }
            if (call == 10)
            {
                result.Title = "Settings opened";
                result.Message = "The guest branch dispatched a low-risk action through the host bridge.";
                return "navigation direct";
            }
            if (call == 11)
            {
                result.Title = "Payment blocked";
                result.Message = "Payment requires confirmation on a trusted device.";
                return "policy blocked payment";
            }
            if (call == 12)
            {
                result.Title = "Voice bridge requested";
                result.Message = "The guest requested a host microphone bridge.";
                return "voice helper";
            }
            result.Title = "Missing host bridge";
            result.Message = "The guest requested hostcall " + call + ", which is not implemented.";
            return "deopt hostcall " + call;
        }
    }
}
