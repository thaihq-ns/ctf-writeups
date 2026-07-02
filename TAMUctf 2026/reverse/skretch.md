# skretch Write-up

**Challenge:** skretch  
**Author:** flocto  
**Category:** Reverse Engineering / Static Analysis / Scratch  
**Author write-up:** c10v3 - V_Tetra team  
**File type:** Scratch / TurboWarp project (`.sb3`) compressed with zstd  
**Method:** Analyze `project.json`, reconstruct the linear checker, solve modulo 257, and recover the target PNG.

## Flag

```text
gigem{g00d_k1tty_4nd_thx_7hom4s}
```

---

## Quick Summary

This is a reverse engineering challenge built inside a Scratch / TurboWarp project.

At first glance, the project only asks the user to select an image file. Internally, however, the project does much more:

1. Reads the selected file as a data URL.
2. Extracts the base64 payload.
3. Decodes the base64 data into bytes.
4. Applies a byte transform to every byte.
5. Checks the transformed bytes against **38,566 linear constraints**.
6. Prints `Looks flaggy!` only if every constraint is satisfied.

The intended input is not a text flag.  
The correct input is an image file. By reconstructing the checker statically, we can recover that image and read the flag from it.

---

## 1. Identifying the Challenge Files

The provided input file is:

```text
skretch_FULL.sb3.zstd
```

This is a Scratch project file, `.sb3`, additionally compressed with zstd.

To unpack it:

```bash
zstd -d skretch_FULL.sb3.zstd -o skretch.sb3
unzip skretch.sb3 -d skretch
```

An `.sb3` file is just a ZIP archive. After extracting it, the most important file is:

```text
project.json
```

In this challenge, `project.json` is extremely large, around 372 MB. This strongly suggests that the checker was generated automatically rather than written manually in Scratch.

When loading `project.json`, two details stand out:

- The second sprite contains roughly 1.7 million blocks.
- The stage has exactly 64 backdrops named:

```text
A-Z
a-z
0-9
+
/
```

This is the standard base64 alphabet.

---

## 2. Overall Project Logic

The main workflow of the Scratch project can be summarized as follows:

1. Use `files_showPickerAs(url)` to read the selected file as a data URL.
2. Locate the comma `,` in the data URL.
3. Keep only the right side, which is the base64 payload.
4. Call a custom block to decode base64 into a list of bytes.
5. Transform each decoded byte:

```python
transformed[i] = (original[i] + i) % 256
```

Here, `i` is 1-indexed, following Scratch list indexing.

6. Run 38,566 linear checks.
7. Add all check failures into an accumulator using `abs(...)`.
8. If the final accumulator is `0`, print:

```text
Looks flaggy!
```

The project does not compare the input with a stored flag string.  
It verifies whether the uploaded image is exactly the expected image.

---

## 3. The Custom Block is a Base64 Decoder

The long custom block initially looks complicated, but after simplifying it, the logic is just a base64 decoder implemented with Scratch blocks.

The important observations are:

- Every 4 base64 characters are converted into one 24-bit value.
- The values `[262144, 4096, 64, 1]` are used, which are:

```text
[64^3, 64^2, 64, 1]
```

- The 24-bit value is split into 3 bytes.
- The resulting bytes are appended to the main list.
- Padding with `=` is handled correctly.

Therefore, we do not need to run Scratch.  
Reading the logic is enough to know that the list after this custom block contains the original file content decoded from base64.

---

## 4. Byte Transform After Decoding

Immediately after base64 decoding, the project modifies every byte in the list.

The transform is:

```python
transformed[i] = (original[i] + i) % 256
```

Because Scratch lists are 1-indexed, `i` starts from `1`.

This is important because the later equations do not apply to the original file bytes.  
They apply to the transformed bytes.

To recover the real file, we must reverse the operation:

```python
original[i] = (transformed[i] - i) % 256
```

---

## 5. Checker Structure

After the byte transform, the project resets an accumulator variable to `0`.

Then it executes **38,566** consecutive blocks of the form:

```text
change variable by abs(...)
```

Each `abs(...)` expression represents one linear equation involving three adjacent unknowns:

```text
a_i * x[i] + b_i * x[i+1] + c_i * x[i+2] = d_i
```

The sequence is cyclic.  
Near the end, the equations wrap around and refer back to `x[1]` and `x[2]`.

Example equations:

| Start index | Equation |
|---:|---|
| `11833` | `48*x[11833] + 146*x[11834] + 132*x[11835] = 50246` |
| `33237` | `182*x[33237] + 82*x[33238] + 92*x[33239] = 33614` |

There are:

```text
38,566 equations
38,566 variables: x[1]..x[38566]
```

Each variable appears exactly three times.

This forms a cyclic banded linear system.

---

## 6. Why Solve Modulo 257?

All `x[i]` values are transformed bytes, so they must be in:

```text
0..255
```

A clean way to solve the system is to work modulo 257.

This works well because:

- `257` is prime.
- `257` is greater than the maximum byte value `255`.
- Every non-zero coefficient from `1..255` has an inverse modulo 257.
- Since the real solution is byte-sized, the solution modulo 257 maps directly back to the real byte values.

From each equation:

```text
a_i * x[i] + b_i * x[i+1] + c_i * x[i+2] = d_i
```

We can solve for `x[i+2]`:

```python
x[i+2] = (d_i - a_i*x[i] - b_i*x[i+1]) * inv(c_i) % 257
```

Now express every value in the sequence as a linear function of the first two unknowns:

```text
x[k] = A[k] * x1 + B[k] * x2 + C[k]
```

The final two wrap-around equations form a 2x2 system.  
Solving that system gives `x1` and `x2`.

After that, we can run the recurrence again and recover all 38,566 transformed bytes.

---

## 7. Restoring the PNG

After solving the system, reverse the byte transform:

```python
original[i] = (x[i] - i) % 256
```

The result is a valid PNG file.

The recovered file starts with the PNG magic bytes:

```text
89 50 4E 47 0D 0A 1A 0A
```

The recovered image is `300x300` pixels.

![Recovered PNG](skretch-writeup-assets/image1.png)

The flag is easier to read after extracting the red channel.

![Red channel extraction](skretch-writeup-assets/image2.png)

From the recovered image, the flag is:

```text
gigem{g00d_k1tty_4nd_thx_7hom4s}
```

A small note: the first character of the last word is `7`, not `t` or `T`.

This matches the leetspeak style used throughout the flag:

```text
g00d
k1tty
4nd
7hom4s
```

---

## 8. Reference Solve Script

The full solve script is included separately as `solve_skretch_clean.py`.

Place the script in the same directory as the extracted `project.json`, then run:

```bash
python solve_skretch_clean.py
```

The script will:

1. Parse the checker blocks from `project.json`.
2. Extract all 38,566 equations.
3. Solve the cyclic system modulo 257.
4. Reverse the Scratch byte transform.
5. Write the recovered image to `recovered.png`.

A shortened version of the core recovery logic is:

```python
MOD = 257
N = 38566

# Each row has:
# a*x[i] + b*x[i+1] + c*x[i+2] = d
#
# Solve recurrence:
x[i+2] = (d - a*x[i] - b*x[i+1]) * pow(c, -1, MOD) % MOD

# After recovering transformed bytes:
original = bytes(((x[i] - i) % 256) for i in range(1, N + 1))
Path("recovered.png").write_bytes(original)
```

---

## 9. Final Notes

This challenge is best classified as **Reverse Engineering**, not Forensics.

Although the solution involves extracting and recovering a PNG file, the core work is reverse engineering the Scratch checker:

```text
Scratch blocks -> base64 decoding -> byte transform -> linear equations -> modulo 257 solve -> PNG recovery
```

The image recovery is only the final output of the reversed checker.

---

## Final Flag

```text
gigem{g00d_k1tty_4nd_thx_7hom4s}
```
