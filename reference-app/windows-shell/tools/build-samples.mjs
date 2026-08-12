import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const samples = path.join(root, "samples");

function crc32(buffer) {
  let value = 0xffffffff;
  for (const byte of buffer) {
    value ^= byte;
    for (let bit = 0; bit < 8; bit += 1) value = (value >>> 1) ^ (0xedb88320 & -(value & 1));
  }
  return (value ^ 0xffffffff) >>> 0;
}

function createZip(entries) {
  const localParts = [];
  const centralParts = [];
  let localOffset = 0;
  const dosTime = (12 << 11) >>> 0;
  const dosDate = (((2026 - 1980) << 9) | (8 << 5) | 4) >>> 0;

  for (const entry of entries) {
    const name = Buffer.from(entry.name.replaceAll("\\", "/"), "utf8");
    const data = Buffer.isBuffer(entry.data) ? entry.data : Buffer.from(entry.data, "utf8");
    const checksum = crc32(data);
    const local = Buffer.alloc(30 + name.length);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x0800, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt16LE(dosTime, 10);
    local.writeUInt16LE(dosDate, 12);
    local.writeUInt32LE(checksum, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);
    name.copy(local, 30);
    localParts.push(local, data);

    const central = Buffer.alloc(46 + name.length);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt16LE(dosTime, 12);
    central.writeUInt16LE(dosDate, 14);
    central.writeUInt32LE(checksum, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt16LE(0, 30);
    central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34);
    central.writeUInt16LE(0, 36);
    central.writeUInt32LE(0, 38);
    central.writeUInt32LE(localOffset, 42);
    name.copy(central, 46);
    centralParts.push(central);
    localOffset += local.length + data.length;
  }

  const centralDirectory = Buffer.concat(centralParts);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralDirectory.length, 12);
  end.writeUInt32LE(localOffset, 16);
  end.writeUInt16LE(0, 20);
  return Buffer.concat([...localParts, centralDirectory, end]);
}

function movz(rd, immediate) {
  return (0xd2800000 | ((immediate & 0xffff) << 5) | (rd & 31)) >>> 0;
}

function cmp(rn, immediate) {
  return (0xf100001f | ((immediate & 0xfff) << 10) | ((rn & 31) << 5)) >>> 0;
}

function branchEq(bytes) {
  return (0x54000000 | (((bytes / 4) & 0x7ffff) << 5)) >>> 0;
}

function hlt(immediate) {
  return (0xd4400000 | ((immediate & 0xffff) << 5)) >>> 0;
}

function assembleGuest() {
  const words = [];
  const labels = new Map();
  const fixups = [];
  const label = (name) => labels.set(name, words.length * 4);
  const emit = (word) => words.push(word >>> 0);
  const beq = (name) => { fixups.push({ index: words.length, name }); emit(0); };

  label("boot");
  emit(movz(0, 27)); emit(hlt(1));
  emit(movz(0, 1)); emit(hlt(2));
  emit(movz(0, 2)); emit(hlt(2));
  emit(movz(0, 3)); emit(hlt(2));
  emit(0xd65f03c0);

  label("command");
  emit(cmp(0, 1)); beq("settings");
  emit(cmp(0, 2)); beq("payment");
  emit(cmp(0, 3)); beq("voice");
  emit(hlt(15)); emit(0xd65f03c0);
  label("settings"); emit(movz(0, 1)); emit(hlt(10)); emit(0xd65f03c0);
  label("payment"); emit(movz(0, 2)); emit(hlt(11)); emit(0xd65f03c0);
  label("voice"); emit(movz(0, 3)); emit(hlt(12)); emit(0xd65f03c0);

  for (const fixup of fixups) {
    const source = fixup.index * 4;
    words[fixup.index] = branchEq(labels.get(fixup.name) - source);
  }
  const code = Buffer.alloc(words.length * 4);
  words.forEach((word, index) => code.writeUInt32LE(word, index * 4));
  return { code, commandOffset: labels.get("command") };
}

function createMachO() {
  const { code, commandOffset } = assembleGuest();
  const header = 32;
  const segment = 152;
  const build = 24;
  const main = 24;
  const commands = segment + build + main;
  const codeOffset = header + commands;
  const fileSize = codeOffset + code.length;
  const buffer = Buffer.alloc(fileSize);
  const writeName = (offset, text) => buffer.write(text, offset, Math.min(16, text.length), "ascii");
  buffer.writeUInt32LE(0xfeedfacf, 0);
  buffer.writeUInt32LE(0x0100000c, 4);
  buffer.writeUInt32LE(0, 8);
  buffer.writeUInt32LE(2, 12);
  buffer.writeUInt32LE(3, 16);
  buffer.writeUInt32LE(commands, 20);
  buffer.writeUInt32LE(1, 24);
  let cursor = 32;
  buffer.writeUInt32LE(0x19, cursor);
  buffer.writeUInt32LE(segment, cursor + 4);
  writeName(cursor + 8, "__TEXT");
  buffer.writeBigUInt64LE(0x100000000n, cursor + 24);
  buffer.writeBigUInt64LE(BigInt(fileSize), cursor + 32);
  buffer.writeBigUInt64LE(0n, cursor + 40);
  buffer.writeBigUInt64LE(BigInt(fileSize), cursor + 48);
  buffer.writeUInt32LE(5, cursor + 56);
  buffer.writeUInt32LE(5, cursor + 60);
  buffer.writeUInt32LE(1, cursor + 64);
  const section = cursor + 72;
  writeName(section, "__text");
  writeName(section + 16, "__TEXT");
  buffer.writeBigUInt64LE(0x100000000n + BigInt(codeOffset), section + 32);
  buffer.writeBigUInt64LE(BigInt(code.length), section + 40);
  buffer.writeUInt32LE(codeOffset, section + 48);
  buffer.writeUInt32LE(2, section + 52);
  buffer.writeUInt32LE(0x80000400, section + 64);
  cursor += segment;
  buffer.writeUInt32LE(0x32, cursor);
  buffer.writeUInt32LE(build, cursor + 4);
  buffer.writeUInt32LE(2, cursor + 8);
  buffer.writeUInt32LE(27 << 16, cursor + 12);
  buffer.writeUInt32LE(27 << 16, cursor + 16);
  cursor += build;
  buffer.writeUInt32LE(0x80000028, cursor);
  buffer.writeUInt32LE(main, cursor + 4);
  buffer.writeBigUInt64LE(BigInt(codeOffset), cursor + 8);
  code.copy(buffer, codeOffset);
  return { buffer, commandOffset };
}

await fs.mkdir(samples, { recursive: true });

const androidManifest = `<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.jidan.demo">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="36" />
  <application android:label="Jidan Android Demo" android:hasCode="true">
    <activity android:name=".MainActivity" android:exported="true" />
  </application>
</manifest>`;
const dex = Buffer.alloc(112);
Buffer.from("dex\n035\0", "binary").copy(dex, 0);
const apk = createZip([
  { name: "AndroidManifest.xml", data: androidManifest },
  { name: "classes.dex", data: dex },
  { name: "META-INF/JIDAN.SF", data: "Clean-room inspection fixture; not signed for device installation.\n" },
]);
await fs.writeFile(path.join(samples, "JidanDemo.apk"), apk);

const guest = createMachO();
const infoPlist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>JidanDemo</string>
  <key>CFBundleIdentifier</key><string>org.jidan.demo</string>
  <key>CFBundleDisplayName</key><string>Jidan iOS Guest</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>`;
const ipa = createZip([
  { name: "Payload/JidanDemo.app/Info.plist", data: infoPlist },
  { name: "Payload/JidanDemo.app/JidanDemo", data: guest.buffer },
  { name: "Payload/JidanDemo.app/JidanRuntime.ini", data: `commandOffset=${guest.commandOffset}\ncleanRoom=true\n` },
]);
await fs.writeFile(path.join(samples, "JidanDemo.ipa"), ipa);

process.stdout.write(`Built samples/JidanDemo.apk (${apk.length} bytes)\nBuilt samples/JidanDemo.ipa (${ipa.length} bytes)\n`);
