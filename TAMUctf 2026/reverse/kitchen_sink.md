# Kitchen Sink Write-up

**Challenge:** kitchen sink  
**Category:** reverse / obfuscation  
**Author write-up:** c10v3 - V_Tetra team  

## Quick Conclusion

**Final flag:**

```text
gigem{h0pefu11Y_This_0n3_last5_m0Re_thaN_4n_h0ur...}
```

The key point of this challenge is that the visible strings inside the binary are bait.  
The real validation logic does not compare the input against a plain flag string.

Instead, the program transforms the user input into **64 Hadamard coefficients** and compares the result against a constant table stored in `.rodata`.

To solve the challenge:

1. Extract the 64-word constant table from `.rodata`.
2. Treat it as the output of a Walsh-Hadamard Transform.
3. Apply the inverse transform.
4. Divide every value by 64.
5. Convert the recovered bytes back to ASCII.

---

## 1. Overview

The given file is a stripped PIE 64-bit ELF binary.

When executed normally, it prints:

```text
flag>
```

A simple `strings` check shows several fake flags, for example:

```text
LAG{d3c0y_fl4g}
flag{keep_running_strings_on_this}
```

These are only decoys.

The binary also contains many anti-debugging and anti-tampering techniques, including:

- Environment variable checks
- Reading `/proc/<ppid>/comm`
- Scanning `/proc/self/maps`
- `fork()` + `ptrace()`
- Code section self-hashing
- Runtime measurement checks

Because of these checks, direct debugging can easily lead to misleading behavior.

---

## 2. Initial Recon

Useful commands for the first analysis:

```bash
file kitchen-sink
strings -a kitchen-sink | less
readelf -hW kitchen-sink
objdump -d -M intel kitchen-sink | less
```

After inspecting the disassembly, the important observation is that the main function does not compare the input directly with a secret string.

Instead, the program performs three main steps:

1. If any anti-debug or anti-tamper check fails, a global variable named `dead` is set to `0xdead`.
2. It calls an indirect function through a function pointer located around `.data + 0x8320`.
3. That function transforms the input into a 64-word array of signed 16-bit values.
4. The transformed output is compared with a 128-byte constant table located at `.rodata + 0x6010`.

The final comparison simply ORs all differences together.  
Therefore, the real pass condition is:

```text
transformed_input[0..63] == target[0..63]
```

---

## 3. Locate the Target Table

Inside the main function, the program copies 128 bytes from `.rodata + 0x6010` to the stack.

This copied data is the target table used for validation.

The table should be interpreted as:

- 64 values
- Signed 16-bit integers
- Little-endian format

The relevant offset is:

```python
TARGET_OFF = 0x6010
TARGET_WORDS = 64
```

So the target data is:

```text
kitchen-sink[0x6010 : 0x6010 + 64 * 2]
```

---

## 4. Identify the Input Transformation

To understand the indirect function at `.data + 0x8320`, I tested it with simple inputs.

When the `dead` variable is cleared before calling this function, the output becomes stable and the transformation pattern is easy to recognize.

| Input | Partial output of 64 words | Comment |
|---|---|---|
| `""` | `0000 0000 0000 0000 ...` | Total zero |
| `A` | `0041 0041 0041 0041 ...` | All coefficients are equal to `0x41` |
| `AB` | `0083 ffff 0083 ffff ...` | `0x83 = A + B`, `0xffff = A - B` |
| `ABCD` | `010a fffe fffc 0000 ...` | Matches Hadamard coefficient behavior |

This pattern matches the **Walsh-Hadamard Transform**, specifically the Sylvester Hadamard transform over a 64-element vector.

The input behavior can be represented as:

```text
x = 64-byte input buffer, padded with NUL bytes
y = H64 * x
```

Where:

- `x` is the original input vector
- `H64` is the 64x64 Hadamard matrix
- `y` is the 64-value transformed output

---

## 5. Reverse the Transform

The Hadamard matrix has a useful property:

```text
H_n^{-1} = H_n / n
```

Because the transform size is 64, the inverse process is:

```text
x = H64 * y / 64
```

So the solution is simple:

1. Read the 64 signed 16-bit coefficients from `.rodata + 0x6010`.
2. Apply the Hadamard transform again.
3. Divide each result by 64.
4. Convert the values to bytes.
5. Strip trailing NUL bytes.

This recovers the original flag.

---

## 6. Solve Script

```python
#!/usr/bin/env python3
import struct
from pathlib import Path

TARGET_OFF = 0x6010
TARGET_WORDS = 64

blob = Path("kitchen-sink").read_bytes()

raw = blob[TARGET_OFF:TARGET_OFF + TARGET_WORDS * 2]
y = [
    struct.unpack_from("<h", raw, i * 2)[0]
    for i in range(TARGET_WORDS)
]

x = y[:]
h = 1

while h < TARGET_WORDS:
    for i in range(0, TARGET_WORDS, h * 2):
        for j in range(i, i + h):
            a = x[j]
            b = x[j + h]
            x[j] = a + b
            x[j + h] = a - b
    h *= 2

x = [v // TARGET_WORDS for v in x]

flag = bytes(x).rstrip(b"\x00").decode()
print(flag)
```

---

## 7. Final Result

Running the solve script gives:

```text
gigem{h0pefu11Y_This_0n3_last5_m0Re_thaN_4n_h0ur...}
```

When this string is entered into the binary, the transformed buffer matches the 64-word table in `.rodata`.

If the anti-debug logic is bypassed correctly, for example by forcing `dead = 0` and making the anti-debug check return success, the program prints:

```text
yep!
```

---

## 8. Why Local Execution May Fail

Local execution may fail because of the binary's anti-debug and anti-instrumentation checks.

If any check fails, the global variable `dead` is set to:

```text
0xdead
```

When this happens, the transformation function no longer returns the true Hadamard transform output.  
Instead, it enters a fake branch and generates 64 random-looking values using `rand()`.

As a result, the transformed output changes between executions and will never match the real target table.

If the output changes every time, it is almost certainly executing the fake branch.

To analyze the real transformation, reset `dead` to `0` before calling the transformation function.

---

## 9. Reproduction Checklist

To reproduce the solution:

1. Open the binary and ignore all decoy flag strings.
2. Locate the 128-byte target table at `.rodata + 0x6010`.
3. Interpret the table as 64 signed 16-bit little-endian values.
4. Identify the input transformation as a 64-point Walsh-Hadamard Transform.
5. Apply the inverse Hadamard transform.
6. Divide all recovered values by 64.
7. Convert the result to bytes.
8. Remove trailing NUL bytes.
9. Obtain the final flag.

---

## Flag

```text
gigem{h0pefu11Y_This_0n3_last5_m0Re_thaN_4n_h0ur...}
```
