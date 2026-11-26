import struct, json, sys

data = open('mod-original.bin','rb').read()
total = struct.unpack('<i', data[:4])[0]
print('header size:', total, 'file len:', len(data), file=sys.stderr)
pos = 4

def parse_entries(end):
    global pos
    obj = {}
    order = []
    while pos < end:
        t = data[pos]; pos += 1
        if t == 0:
            return obj, order
        kend = data.index(b'\x00', pos)
        key = data[pos:kend].decode('utf-8', 'replace'); pos = kend + 1
        if t == 0x01:
            val = struct.unpack('<d', data[pos:pos+8])[0]; pos += 8
        elif t == 0x02:
            ln = struct.unpack('<i', data[pos:pos+4])[0]; pos += 4
            raw = data[pos:pos+ln]; pos += ln
            val = raw[:-1].decode('utf-8', 'replace') if raw.endswith(b'\x00') else raw.decode('utf-8','replace')
        elif t in (0x03, 0x04):
            ln = struct.unpack('<i', data[pos:pos+4])[0]; pos += 4
            sub_end = pos - 4 + ln  # length includes its own 4 bytes
            val, _ = parse_entries(sub_end)
            if pos != sub_end:
                print(f'WARN {key}: consumed to {pos}, expected end {sub_end}', file=sys.stderr)
                pos = sub_end
            if t == 0x04:
                val = [val[str(i)] for i in range(len(val))]
        elif t == 0x08:
            val = bool(data[pos]); pos += 1
        elif t == 0x10:
            val = struct.unpack('<i', data[pos:pos+4])[0]; pos += 4
        elif t == 0x12:
            val = struct.unpack('<q', data[pos:pos+8])[0]; pos += 8
        else:
            raise ValueError(f'unknown type {t:#x} at {pos-1} key {key!r}')
        obj[key] = val; order.append(key)
    return obj, order

root, _ = parse_entries(len(data))
print('final pos:', pos, 'len:', len(data), file=sys.stderr)
json.dump(root, open('mod.json','w'), indent=1)
print('top keys:', list(root.keys()))
print('ObjectStates:', len(root.get('ObjectStates', [])))
