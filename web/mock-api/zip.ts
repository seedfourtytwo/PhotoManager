/** Minimal ZIP writer (stored, no compression — photos don't compress), for the mock only. */

const CRC_TABLE = (() => {
	const table = new Uint32Array(256);
	for (let n = 0; n < 256; n++) {
		let c = n;
		for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
		table[n] = c >>> 0;
	}
	return table;
})();

export function crc32(data: Uint8Array): number {
	let c = 0xffffffff;
	for (const byte of data) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
	return (c ^ 0xffffffff) >>> 0;
}

type ZipEntry = { name: string; data: Uint8Array };

export function zip(entries: ZipEntry[]): Buffer {
	const chunks: Buffer[] = [];
	const central: Buffer[] = [];
	let offset = 0;
	const dosTime = 0;
	const dosDate = ((2026 - 1980) << 9) | (9 << 5) | 29;
	for (const entry of entries) {
		const name = Buffer.from(entry.name, 'utf8');
		const crc = crc32(entry.data);
		const local = Buffer.alloc(30);
		local.writeUInt32LE(0x04034b50, 0);
		local.writeUInt16LE(20, 4);
		local.writeUInt16LE(0x0800, 6); // UTF-8 names
		local.writeUInt16LE(0, 8); // stored
		local.writeUInt16LE(dosTime, 10);
		local.writeUInt16LE(dosDate, 12);
		local.writeUInt32LE(crc, 14);
		local.writeUInt32LE(entry.data.length, 18);
		local.writeUInt32LE(entry.data.length, 22);
		local.writeUInt16LE(name.length, 26);
		chunks.push(local, name, Buffer.from(entry.data));

		const dir = Buffer.alloc(46);
		dir.writeUInt32LE(0x02014b50, 0);
		dir.writeUInt16LE(20, 4);
		dir.writeUInt16LE(20, 6);
		dir.writeUInt16LE(0x0800, 8);
		dir.writeUInt16LE(0, 10);
		dir.writeUInt16LE(dosTime, 12);
		dir.writeUInt16LE(dosDate, 14);
		dir.writeUInt32LE(crc, 16);
		dir.writeUInt32LE(entry.data.length, 20);
		dir.writeUInt32LE(entry.data.length, 24);
		dir.writeUInt16LE(name.length, 28);
		dir.writeUInt32LE(offset, 42);
		central.push(dir, name);
		offset += 30 + name.length + entry.data.length;
	}
	const dirSize = central.reduce((n, b) => n + b.length, 0);
	const end = Buffer.alloc(22);
	end.writeUInt32LE(0x06054b50, 0);
	end.writeUInt16LE(entries.length, 8);
	end.writeUInt16LE(entries.length, 10);
	end.writeUInt32LE(dirSize, 12);
	end.writeUInt32LE(offset, 16);
	return Buffer.concat([...chunks, ...central, end]);
}
