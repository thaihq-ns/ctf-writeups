import json
import math
from pathlib import Path

PROJECT_JSON = Path('project.json')
OUT_PNG = Path('recovered.png')
N = 38566
LIST_ID = 'Ob7NZ-wVNV~SOQ26}pkG'
MOD = 257

def scratch_num_to_str(x: float) -> str:
    if math.isnan(x):
        return 'NaN'
    if math.isinf(x):
        return 'Infinity' if x > 0 else '-Infinity'
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f'{x:.15g}'

def js_round(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        return x
    return math.floor(x + 0.5) if x >= 0 else math.ceil(x - 0.5)

class Affine:
    """Affine form: const + sum(coeff[i] * x[i])."""
    __slots__ = ('const', 'coeff')

    def __init__(self, const: float = 0.0, coeff=None):
        self.const = float(const)
        self.coeff = dict(coeff or {})

    def is_const(self) -> bool:
        return not self.coeff

    def __add__(self, other: 'Affine') -> 'Affine':
        out = Affine(self.const + other.const, self.coeff.copy())
        for k, v in other.coeff.items():
            out.coeff[k] = out.coeff.get(k, 0.0) + v
        out.coeff = {k: v for k, v in out.coeff.items() if abs(v) > 1e-9}
        return out

    def __sub__(self, other: 'Affine') -> 'Affine':
        out = Affine(self.const - other.const, self.coeff.copy())
        for k, v in other.coeff.items():
            out.coeff[k] = out.coeff.get(k, 0.0) - v
        out.coeff = {k: v for k, v in out.coeff.items() if abs(v) > 1e-9}
        return out

    def scale(self, k: float) -> 'Affine':
        return Affine(self.const * k, {i: c * k for i, c in self.coeff.items()})

def solve(project_json: Path = PROJECT_JSON, out_png: Path = OUT_PNG) -> str:
    data = json.loads(project_json.read_text(encoding='utf-8'))
    blocks = data['targets'][1]['blocks']
    cache = {}

    def as_num(value) -> float:
        if isinstance(value, Affine) and value.is_const():
            return value.const
        raise ValueError(f'Not numeric constant: {value!r}')

    def as_str(value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, Affine) and value.is_const():
            return scratch_num_to_str(value.const)
        raise ValueError(f'Not string constant: {value!r}')

    def parse_input(inp):
        if not isinstance(inp, list) or len(inp) < 2:
            raise ValueError(f'Unknown input format: {inp!r}')
        if isinstance(inp[1], str) and inp[1] in blocks:
            return parse_block(inp[1])
        if isinstance(inp[1], list):
            literal = inp[1]
            tag = literal[0]
            if tag in (4, 5, 6, 7, 8):
                return Affine(float(literal[1]))
            if tag in (10, 11):
                return str(literal[1])
        raise ValueError(f'Unsupported input: {inp!r}')

    def parse_block(block_id):
        if block_id in cache:
            return cache[block_id]

        block = blocks[block_id]
        op = block['opcode']
        fields = block.get('fields', {})
        inputs = block.get('inputs', {})
        g = lambda name: parse_input(inputs[name])

        if op == 'operator_add':
            result = g('NUM1') + g('NUM2')
        elif op == 'operator_subtract':
            result = g('NUM1') - g('NUM2')
        elif op == 'operator_multiply':
            a, b = g('NUM1'), g('NUM2')
            if a.is_const():
                result = b.scale(a.const)
            elif b.is_const():
                result = a.scale(b.const)
            else:
                raise ValueError(f'Nonlinear multiply at {block_id}')
        elif op == 'operator_divide':
            a, b = g('NUM1'), g('NUM2')
            if b.const == 0:
                result = Affine(float('inf') if a.const > 0 else float('-inf'))
            else:
                result = a.scale(1.0 / b.const)
        elif op == 'operator_mod':
            a, b = g('NUM1'), g('NUM2')
            if not (a.is_const() and b.is_const()):
                raise ValueError(f'Nonlinear modulo at {block_id}')
            result = Affine(a.const % b.const)
        elif op == 'operator_round':
            result = Affine(js_round(as_num(g('NUM'))))
        elif op == 'operator_gt':
            result = Affine(1.0 if as_num(g('OPERAND1')) > as_num(g('OPERAND2')) else 0.0)
        elif op == 'operator_lt':
            result = Affine(1.0 if as_num(g('OPERAND1')) < as_num(g('OPERAND2')) else 0.0)
        elif op == 'operator_equals':
            left, right = g('OPERAND1'), g('OPERAND2')
            if isinstance(left, str) or isinstance(right, str):
                result = Affine(1.0 if as_str(left) == as_str(right) else 0.0)
            else:
                result = Affine(1.0 if abs(as_num(left) - as_num(right)) < 1e-9 else 0.0)
        elif op == 'operator_not':
            result = Affine(0.0 if as_num(g('OPERAND')) else 1.0)
        elif op == 'operator_join':
            result = as_str(g('STRING1')) + as_str(g('STRING2'))
        elif op == 'operator_length':
            result = Affine(float(len(as_str(g('STRING')))))
        elif op == 'operator_letter_of':
            index = int(as_num(g('LETTER')))
            s = as_str(g('STRING'))
            result = s[index - 1] if 1 <= index <= len(s) else ''
        elif op == 'operator_mathop':
            name = fields['OPERATOR'][0]
            if name == 'abs':
                result = ('ABS', parse_input(inputs['NUM']))
            else:
                x = as_num(g('NUM'))
                if name == 'floor':
                    result = Affine(float(math.floor(x)))
                elif name == 'ceiling':
                    result = Affine(float(math.ceil(x)))
                elif name == 'sqrt':
                    result = Affine(math.sqrt(x))
                elif name == 'e ^':
                    result = Affine(math.e ** x)
                elif name == '10 ^':
                    result = Affine(10 ** x)
                elif name == 'tan':
                    result = Affine(math.tan(math.radians(x)))
                elif name == 'ln':
                    result = Affine(math.log(x))
                else:
                    raise ValueError(f'Unknown mathop {name}')
        elif op == 'data_itemoflist':
            if fields['LIST'][1] != LIST_ID:
                raise ValueError('Unexpected list id')
            index = int(round(as_num(g('INDEX'))))
            result = Affine(0.0, {index: 1.0})
        else:
            raise ValueError(f'Unexpected opcode: {op}')

        cache[block_id] = result
        return result

    def equation_from_change_block(change_block_id):
        value_block_id = blocks[change_block_id]['inputs']['VALUE'][1]
        value_block = blocks[value_block_id]
        assert value_block['opcode'] == 'operator_mathop'
        assert value_block['fields']['OPERATOR'][0] == 'abs'
        inner = parse_input(value_block['inputs']['NUM'])
        assert isinstance(inner, Affine)
        return inner

    rows = [None] * N
    block_id = '+Tqe<s-qzLBT'

    while block_id != 'd':
        aff = equation_from_change_block(block_id)
        idx = sorted(aff.coeff)
        rhs = int(round(-aff.const))

        if idx == [1, 2, N]:
            start = N
            ordered = [(N, aff.coeff[N]), (1, aff.coeff[1]), (2, aff.coeff[2])]
        elif idx == [1, N - 1, N]:
            start = N - 1
            ordered = [(N - 1, aff.coeff[N - 1]), (N, aff.coeff[N]), (1, aff.coeff[1])]
        else:
            start = idx[0]
            ordered = [(start, aff.coeff[start]), (start + 1, aff.coeff[start + 1]), (start + 2, aff.coeff[start + 2])]

        rows[start - 1] = ([int(round(c)) for _, c in ordered], rhs)
        block_id = blocks[block_id]['next']

    inv = {a: pow(a, -1, MOD) for a in range(1, MOD)}

    A = [0] * (N + 1)
    B = [0] * (N + 1)
    C = [0] * (N + 1)

    A[1], B[1], C[1] = 1, 0, 0
    A[2], B[2], C[2] = 0, 1, 0

    for i in range(1, N - 1):
        (a, b, c), d = rows[i - 1]
        c_inv = inv[c % MOD]
        A[i + 2] = ((-a * A[i] - b * A[i + 1]) * c_inv) % MOD
        B[i + 2] = ((-a * B[i] - b * B[i + 1]) * c_inv) % MOD
        C[i + 2] = ((d - a * C[i] - b * C[i + 1]) * c_inv) % MOD

    (a1, b1, c1), d1 = rows[N - 2]
    (a2, b2, c2), d2 = rows[N - 1]

    M11 = (a1 * A[N - 1] + b1 * A[N] + c1) % MOD
    M12 = (a1 * B[N - 1] + b1 * B[N]) % MOD
    R1 = (d1 - a1 * C[N - 1] - b1 * C[N]) % MOD

    M21 = (a2 * A[N] + b2) % MOD
    M22 = (a2 * B[N] + c2) % MOD
    R2 = (d2 - a2 * C[N]) % MOD

    det = (M11 * M22 - M12 * M21) % MOD
    det_inv = pow(det, -1, MOD)

    x1 = ((R1 * M22 - M12 * R2) * det_inv) % MOD
    x2 = ((M11 * R2 - R1 * M21) * det_inv) % MOD

    x = [0] * (N + 1)
    x[1], x[2] = x1, x2

    for i in range(1, N - 1):
        (a, b, c), d = rows[i - 1]
        x[i + 2] = ((d - a * x[i] - b * x[i + 1]) * inv[c % MOD]) % MOD

    original = bytes(((x[i] - i) % 256) for i in range(1, N + 1))
    out_png.write_bytes(original)

    return 'gigem{g00d_k1tty_4nd_thx_7hom4s}'

if __name__ == '__main__':
    flag = solve()
    print(flag)
