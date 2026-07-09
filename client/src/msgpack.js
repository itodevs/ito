const TEXT_ENCODER = new TextEncoder();
const TEXT_DECODER = new TextDecoder();

export function encodeMessagePack(value) {
  const writer = new MessagePackWriter();
  writer.write(value);
  return writer.toUint8Array();
}

export function decodeMessagePack(bytes) {
  const reader = new MessagePackReader(bytes);
  const value = reader.read();
  if (reader.offset !== reader.bytes.length) {
    throw new Error("invalid MessagePack: trailing bytes");
  }
  return value;
}

class MessagePackWriter {
  constructor() {
    this.bytes = [];
  }

  toUint8Array() {
    return new Uint8Array(this.bytes);
  }

  write(value) {
    if (value === null || value === undefined) {
      this.push(0xc0);
    } else if (typeof value === "boolean") {
      this.push(value ? 0xc3 : 0xc2);
    } else if (typeof value === "number") {
      this.writeNumber(value);
    } else if (typeof value === "string") {
      this.writeString(value);
    } else if (value instanceof Uint8Array) {
      this.writeBinary(value);
    } else if (Array.isArray(value)) {
      this.writeArray(value);
    } else if (typeof value === "object") {
      this.writeMap(value);
    } else {
      throw new Error(`unsupported MessagePack value: ${typeof value}`);
    }
  }

  writeNumber(value) {
    if (Number.isInteger(value) && value >= 0 && value <= 0x7f) {
      this.push(value);
    } else if (Number.isInteger(value) && value >= -32 && value < 0) {
      this.push(0xe0 | (value + 32));
    } else if (Number.isInteger(value) && value >= 0 && value <= 0xff) {
      this.push(0xcc, value);
    } else if (Number.isInteger(value) && value >= 0 && value <= 0xffff) {
      this.push(0xcd, value >> 8, value);
    } else if (Number.isInteger(value) && value >= -0x80000000 && value <= 0x7fffffff) {
      this.push(0xd2);
      this.writeInt32(value);
    } else {
      const buffer = new ArrayBuffer(9);
      const view = new DataView(buffer);
      view.setUint8(0, 0xcb);
      view.setFloat64(1, value, false);
      this.pushBytes(new Uint8Array(buffer));
    }
  }

  writeString(value) {
    const bytes = TEXT_ENCODER.encode(value);
    if (bytes.length <= 31) {
      this.push(0xa0 | bytes.length);
    } else if (bytes.length <= 0xff) {
      this.push(0xd9, bytes.length);
    } else if (bytes.length <= 0xffff) {
      this.push(0xda, bytes.length >> 8, bytes.length);
    } else {
      this.push(0xdb);
      this.writeUint32(bytes.length);
    }
    this.pushBytes(bytes);
  }

  writeBinary(value) {
    if (value.length <= 0xff) {
      this.push(0xc4, value.length);
    } else if (value.length <= 0xffff) {
      this.push(0xc5, value.length >> 8, value.length);
    } else {
      this.push(0xc6);
      this.writeUint32(value.length);
    }
    this.pushBytes(value);
  }

  writeArray(value) {
    if (value.length <= 15) {
      this.push(0x90 | value.length);
    } else if (value.length <= 0xffff) {
      this.push(0xdc, value.length >> 8, value.length);
    } else {
      this.push(0xdd);
      this.writeUint32(value.length);
    }
    for (const item of value) {
      this.write(item);
    }
  }

  writeMap(value) {
    const entries = Object.entries(value).filter(([, entryValue]) => entryValue !== undefined);
    if (entries.length <= 15) {
      this.push(0x80 | entries.length);
    } else if (entries.length <= 0xffff) {
      this.push(0xde, entries.length >> 8, entries.length);
    } else {
      this.push(0xdf);
      this.writeUint32(entries.length);
    }
    for (const [key, entryValue] of entries) {
      this.writeString(key);
      this.write(entryValue);
    }
  }

  writeInt32(value) {
    this.push((value >> 24) & 0xff, (value >> 16) & 0xff, (value >> 8) & 0xff, value & 0xff);
  }

  writeUint32(value) {
    this.push((value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff);
  }

  push(...values) {
    for (const value of values) {
      this.bytes.push(value & 0xff);
    }
  }

  pushBytes(values) {
    for (const value of values) {
      this.bytes.push(value);
    }
  }
}

class MessagePackReader {
  constructor(bytes) {
    this.bytes = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    this.offset = 0;
  }

  read() {
    const marker = this.readByte();
    if (marker <= 0x7f) return marker;
    if (marker >= 0xe0) return marker - 0x100;
    if ((marker & 0xe0) === 0xa0) return this.readString(marker & 0x1f);
    if ((marker & 0xf0) === 0x90) return this.readArray(marker & 0x0f);
    if ((marker & 0xf0) === 0x80) return this.readMap(marker & 0x0f);

    switch (marker) {
      case 0xc0:
        return null;
      case 0xc2:
        return false;
      case 0xc3:
        return true;
      case 0xc4:
        return this.readBinary(this.readByte());
      case 0xc5:
        return this.readBinary(this.readUint16());
      case 0xc6:
        return this.readBinary(this.readUint32());
      case 0xca:
        return this.readFloat32();
      case 0xcb:
        return this.readFloat64();
      case 0xcc:
        return this.readByte();
      case 0xcd:
        return this.readUint16();
      case 0xce:
        return this.readUint32();
      case 0xd0:
        return this.readInt8();
      case 0xd1:
        return this.readInt16();
      case 0xd2:
        return this.readInt32();
      case 0xd9:
        return this.readString(this.readByte());
      case 0xda:
        return this.readString(this.readUint16());
      case 0xdb:
        return this.readString(this.readUint32());
      case 0xdc:
        return this.readArray(this.readUint16());
      case 0xdd:
        return this.readArray(this.readUint32());
      case 0xde:
        return this.readMap(this.readUint16());
      case 0xdf:
        return this.readMap(this.readUint32());
      default:
        throw new Error(`unsupported MessagePack marker: 0x${marker.toString(16)}`);
    }
  }

  readString(length) {
    return TEXT_DECODER.decode(this.readBytes(length));
  }

  readBinary(length) {
    return this.readBytes(length);
  }

  readArray(length) {
    const value = [];
    for (let index = 0; index < length; index += 1) {
      value.push(this.read());
    }
    return value;
  }

  readMap(length) {
    const value = {};
    for (let index = 0; index < length; index += 1) {
      const key = this.read();
      value[key] = this.read();
    }
    return value;
  }

  readByte() {
    if (this.offset >= this.bytes.length) {
      throw new Error("invalid MessagePack: unexpected end of input");
    }
    return this.bytes[this.offset++];
  }

  readBytes(length) {
    if (this.offset + length > this.bytes.length) {
      throw new Error("invalid MessagePack: unexpected end of input");
    }
    const slice = this.bytes.slice(this.offset, this.offset + length);
    this.offset += length;
    return slice;
  }

  readUint16() {
    return (this.readByte() << 8) | this.readByte();
  }

  readUint32() {
    return (
      (this.readByte() * 0x1000000) +
      ((this.readByte() << 16) | (this.readByte() << 8) | this.readByte())
    );
  }

  readInt8() {
    const value = this.readByte();
    return value & 0x80 ? value - 0x100 : value;
  }

  readInt16() {
    const value = this.readUint16();
    return value & 0x8000 ? value - 0x10000 : value;
  }

  readInt32() {
    const value = this.readUint32();
    return value > 0x7fffffff ? value - 0x100000000 : value;
  }

  readFloat32() {
    const bytes = this.readBytes(4);
    return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getFloat32(0, false);
  }

  readFloat64() {
    const bytes = this.readBytes(8);
    return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getFloat64(0, false);
  }
}
