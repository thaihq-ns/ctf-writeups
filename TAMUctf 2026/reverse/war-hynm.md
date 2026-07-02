# War Hymn Write-up

**Challenge:** War Hymn  
**Category:** reverse engineering / ELF unpacking / crypto  
**Author:** Archan6el  
**Author write-up:** c10v3 - V_Tetra team  
**Analysis file:** `war-hymn`  
**File type:** ELF 64-bit, stripped  
**Approach:** Static-first analysis: extract sections, decode offline, avoid relying on direct execution  

## Flag

```text
gigem{sh0uld_h4v3_r4n_th3_b411_0n_f1r$t_4nd_g04l!!!}
```

---

## Quick Summary

The main binary does not contain the flag as a normal string.

Instead, it performs several layers of unpacking and decryption:

1. The main ELF decodes section names using lyrics from **Aggie War Hymn**.
2. It loads a 71-byte decoder stub from the ELF itself.
3. That stub decodes a `0xC42`-byte blob.
4. The decoded blob contains a zlib-compressed shared object.
5. The program extracts the shared object into memory using `memfd_create`.
6. It loads the shared object with `dlopen`.
7. The shared object uses RC4 to decrypt several embedded strings.
8. The final decrypted string is the flag.

The important point is that the flag is not inside the main ELF directly.  
It is inside the unpacked shared object.

---

## 1. Initial Direction

After unpacking the challenge archive, we only get one executable file:

```text
war-hymn
```

Running it directly in an unstable analysis environment may cause crashes or misleading behavior because the binary includes anti-debugging logic.

For that reason, the safest method is to analyze the ELF structure, extract suspicious sections, and reproduce each decryption layer offline.

Basic file information:

| Item | Value |
|---|---|
| File | `war-hymn` |
| Type | ELF 64-bit LSB executable |
| Architecture | x86-64 |
| Linking | Dynamically linked |
| Stripped | Yes |
| BuildID | `db7ab7c34b17b91aa3d466ccd7d3127a018c2e11` |
| File size | 30104 bytes |

Notable imported or referenced items:

```text
libz.so.1
memfd_create
dlopen
dlsym
inflate
/proc/self/status
```

Useful initial command:

```bash
strings -a war-hymn | egrep "inflate|memfd_create|dlopen|TracerPid|LD_PRELOAD"
```

Expected output includes:

```text
inflate
memfd_create
dlopen
TracerPid:
LD_PRELOAD
```

These strings give three strong signals:

1. `TracerPid:` and `LD_PRELOAD` indicate anti-debugging checks.
2. `inflate` indicates zlib decompression.
3. `memfd_create`, `dlopen`, and `dlsym` indicate that the program likely unpacks and loads a shared object from memory.

---

## 2. Suspicious ELF Sections

Running `readelf -S` reveals three important custom sections.

| Section | Size | Role |
|---|---:|---|
| `.init.checksum.validation` | `0x47` / 71 bytes | Small decoder stub. It is mapped as executable and called like a function. |
| `.bss.secure.buffer` | `0xC42` / 3138 bytes | Encoded stage-1 blob containing a header and a zlib stream. |
| `.init.constructors.global` | `0x30D` / 781 bytes | Contains another copy of the War Hymn lyrics, used as a keystream. |

Despite the section names, these are not normal initialization or BSS sections.  
They are part of the unpacking pipeline.

---

## 3. Decoding Hidden Strings in the Main ELF

The main function is located around:

```text
0x4014b0
```

It does not directly reference sensitive strings such as paths and section names.

Instead, encrypted constants are placed on the stack and decrypted byte-by-byte using War Hymn data stored in `.data`.

The decoding formula is:

```c
decoded[i] = encoded[i] ^ ((war_hymn_1[i] + 0x15) & 0xff);
```

The decoded strings are:

| Blob | Decoded value | Purpose |
|---|---|---|
| `#1` | `/proc/self/exe` | Re-open the running binary. |
| `#2` | `.init.checksum.validation` | Section containing the 71-byte decoder stub. |
| `#3` | `.bss.secure.buffer` | Section containing the large encoded blob. |
| `#4` | `.init.constructors.global` | Section containing the second War Hymn keystream. |
| `#5` | `/proc/self/fd` | Used to build a path for loading the memfd. |
| `#6` | `those_who_know` | Virtual filename used for the memfd. |

---

## 4. First Anti-Debug Layer

The main ELF checks for signs of debugging or instrumentation.

Important checks include:

- `LD_PRELOAD`
- `/proc/self/status`
- `TracerPid`

If `LD_PRELOAD` exists or `TracerPid != 0`, the program modifies bytes in the encoded blobs before decoding them.

As a result, the decoded section names and paths become corrupted, causing the unpacking pipeline to fail.

This is the main reason the challenge is better solved statically instead of by following the runtime path directly.

---

## 5. Main ELF Helper Functions

Two helper functions are especially important.

### Function at `0x401b70`

This function loads a section from the ELF, maps it as executable memory, and returns a function pointer.

The function pointer is later stored indirectly through a pointer near:

```text
0x405160
```

This is used to load the decoder stub from:

```text
.init.checksum.validation
```

### Function at `0x401d90`

This function loads an arbitrary section from the ELF into heap memory and returns the buffer plus size.

It is used to load:

```text
.bss.secure.buffer
.init.constructors.global
```

The high-level logic of `main` is:

```python
stub_ptr = load_exec_section("/proc/self/exe", ".init.checksum.validation")

blob, blob_len = read_section(
    ".bss.secure.buffer",
    "/proc/self/exe"
)

key2, key2_len = read_section(
    ".init.constructors.global",
    "/proc/self/exe"
)

stub_ptr(
    blob,
    blob_len,
    out_buf,
    key2,
    key2_len - 1
)
```

---

## 6. Analyzing the 71-byte Decoder Stub

The section `.init.checksum.validation` is not actually a checksum validation section.

It contains a short decoder stub.

The stub receives:

1. The encoded blob
2. The blob length
3. An output buffer
4. The second War Hymn keystream
5. The keystream length

The decoder logic can be represented as:

```python
state = 0x67

for i in range(n):
    state = (state + key2[i % key2_len] + i) & 0xffffffff
    out[i] = enc[i] ^ (state & 0xff)
```

When this decoder is applied to `.bss.secure.buffer`, the output begins with:

```text
42 0c 00 00 3a 0c 00 00 78 9c ...
```

This reveals the stage-1 structure:

```text
42 0c 00 00    total_len = 0x0c42
3a 0c 00 00    zlib_len  = 0x0c3a
78 9c          zlib header
```

| Field | Value |
|---|---:|
| Stage-1 decoded size | `0x0C42` / 3138 bytes |
| Zlib stream length | `0x0C3A` / 3130 bytes |
| Zlib stream offset | `0x08` |
| Inflate result | `payload.so` |
| Inflated size | 16440 bytes |

---

## 7. Second Unpacking Layer: Shared Object Loaded from Memory

After the stage-1 blob is decoded, the main binary calls a wrapper around:

```text
0x4020f0
```

This wrapper inflates the zlib stream into an ELF shared object.

Then it:

1. Creates an anonymous file using `memfd_create`.
2. Writes the shared object into that memfd.
3. Builds a path through `/proc/self/fd/<fd>`.
4. Loads it with `dlopen`.
5. Resolves the symbol `run` using `dlsym`.
6. Calls `run()`.

The high-level logic is:

```python
payload = zlib.decompress(stage1[8 : 8 + zlib_len])

fd = memfd_create("those_who_know", 0)
write(fd, payload)

handle = dlopen(f"/proc/self/fd/{fd}", RTLD_NOW)
run = dlsym(handle, "run")

run()
```

Fortunately, the extracted shared object is not fully stripped.

Useful symbols include:

```text
tracerpid_anti_debug
perform_check
check1
check2
check3
run
```

---

## 8. Second Anti-Debug Layer

The shared object also performs an anti-debug check using `TracerPid`.

If a tracer is detected, the `run` function corrupts the decryption process by:

1. XORing the key with `0x13`
2. XORing the target buffer with `0x21`

This causes all decoded strings to become incorrect.

This is the second mechanism used to prevent straightforward dynamic analysis.

---

## 9. Shared Object Logic: `perform_check` is RC4

The function:

```text
perform_check(0x12ae)
```

implements classic RC4.

It performs:

1. RC4 KSA, initializing array `S` from `0..255`
2. Key scheduling using the provided key
3. RC4 PRGA to XOR the target data

The RC4 key is:

```text
AggiesAggiesAggies
```

| Item | Value |
|---|---|
| Algorithm | RC4 |
| Key | `AggiesAggiesAggies` |
| Key length | 18 bytes |

The shared object contains several encrypted blobs.

The first three are only hints.  
The fourth blob contains the real flag.

| Blob | Length | RC4 result |
|---|---:|---|
| `data1` | `0x12` | `Yeah, this aint it` |
| `data2` | `0x0F` | `Keep going bruh` |
| `data3` | `0x11` | `Are we there yet?` |
| `data4` | `0x34` | `gigem{sh0uld_h4v3_r4n_th3_b411_0n_f1r$t_4nd_g04l!!!}` |

Depending on whether the value is viewed as a virtual address or a file offset, the final blob may appear around:

```text
VA:        0x40e0
File off:  0x30e0
```

In the PoC below, the file offset is used:

```python
data4 = payload[0x30e0:0x30e0 + 0x34]
```

---

## 10. Full Offline Solve Script

The following script reproduces the full chain offline:

1. Dumps the custom ELF sections.
2. Decodes the stage-1 blob using the 71-byte stub logic.
3. Inflates the embedded shared object.
4. Extracts the encrypted flag blob.
5. RC4-decrypts the final flag.

```python
from pathlib import Path
import subprocess
import struct
import zlib

work = Path(".")
exe = work / "war-hymn"

subprocess.run([
    "objcopy",
    "--dump-section", ".data=data.bin",
    "--dump-section", ".init.constructors.global=key2.bin",
    "--dump-section", ".bss.secure.buffer=blob.bin",
    str(exe)
], check=True)

song1 = Path("data.bin").read_bytes()[0x28:]
key2 = Path("key2.bin").read_bytes()[:-1]
blob = Path("blob.bin").read_bytes()

def decode_const(enc):
    return bytes(
        ((song1[i] + 0x15) & 0xff) ^ enc[i]
        for i in range(len(enc))
    )

# Example: decode one encrypted constant from main.
enc = struct.pack("<QIH", 0x1ff0593b5a33f4ab, 0x5019e614, 0x1320)
print(decode_const(enc))  # b'/proc/self/exe'

# Decode .bss.secure.buffer using the 71-byte stub logic.
state = 0x67
stage1 = bytearray(len(blob))

for i, b in enumerate(blob):
    state = (state + key2[i % len(key2)] + i) & 0xffffffff
    stage1[i] = b ^ (state & 0xff)

# Parse stage-1 header and inflate payload.so.
total_len = int.from_bytes(stage1[0:4], "little")
zlen = int.from_bytes(stage1[4:8], "little")

payload = zlib.decompress(stage1[8:8 + zlen])
Path("payload.so").write_bytes(payload)

print(f"stage1 total_len = 0x{total_len:x}")
print(f"zlib length      = 0x{zlen:x}")
print(f"payload.so size  = {len(payload)} bytes")

# RC4 key used by payload.so.
key = b"AggiesAggiesAggies"

# Final encrypted blob.
data4 = payload[0x30e0:0x30e0 + 0x34]

def rc4(buf, key):
    S = list(range(256))
    j = 0

    # KSA
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xff
        S[i], S[j] = S[j], S[i]

    # PRGA
    i = 0
    j = 0
    out = bytearray()

    for b in buf:
        i = (i + 1) & 0xff
        j = (j + S[i]) & 0xff
        S[i], S[j] = S[j], S[i]

        k = S[(S[i] + S[j]) & 0xff]
        out.append(b ^ k)

    return bytes(out)

flag = rc4(data4, key).decode()
print(flag)
```

Expected output:

```text
gigem{sh0uld_h4v3_r4n_th3_b411_0n_f1r$t_4nd_g04l!!!}
```

---

## 11. Summary

This challenge has four main layers.

| Layer | Description |
|---|---|
| Layer 1 | Main ELF decodes path and section names using War Hymn lyrics. |
| Layer 2 | A 71-byte decoder stub uses a second War Hymn section as a keystream. |
| Layer 3 | The decoded stage-1 blob contains a zlib stream that inflates into `payload.so`. |
| Layer 4 | `payload.so` uses RC4 with key `AggiesAggiesAggies` to decrypt the final flag. |

The most interesting part of the challenge is that **Aggie War Hymn** is used as both bait and decoding material.

One copy of the lyrics is used to decode strings and section names in the main ELF.  
Another copy is stored in a custom section and used as the keystream for the 71-byte decoder stub.

The final flag is recovered only after unpacking the shared object and solving the RC4 layer.

---

## Final Flag

```text
gigem{sh0uld_h4v3_r4n_th3_b411_0n_f1r$t_4nd_g04l!!!}
```
