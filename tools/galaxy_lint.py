"""Cheap structural checks for Galaxy source (no type checking: the game compiles it).

Checks balanced braces/parentheses and that every GhostOps_* function is declared
(defined or prototyped) before it is called.
"""
import re


def strip(src):
    """Remove comments and string literals, keeping line structure."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if src.startswith('//', i):
            while i < n and src[i] != '\n':
                i += 1
        elif src.startswith('/*', i):
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append('\n' * src.count('\n', i, j))
            i = j
        elif c == '"':
            i += 1
            while i < n and src[i] != '"':
                i += 2 if src[i] == '\\' else 1
            i += 1
            out.append('""')
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def lint(src, prefix='GhostOps_'):
    problems = []
    s = strip(src)
    for a, b in ('{}', '()', '[]'):
        depth = 0
        for ch in s:
            if ch == a:
                depth += 1
            elif ch == b:
                depth -= 1
                if depth < 0:
                    problems.append('unbalanced %s%s: extra %s' % (a, b, b))
                    break
        if depth > 0:
            problems.append('unbalanced %s%s: %d unclosed %s' % (a, b, depth, a))
    decl = re.compile(r'^\s*(?:void|bool|int|fixed|string|unit|point|trigger|unitgroup|unitfilter|text|bank|sound|soundlink)\s+(' + prefix + r'\w+)\s*\(', re.M)
    declared = {}
    for m in decl.finditer(s):
        declared.setdefault(m.group(1), m.start())
    for m in re.finditer(r'\b(' + prefix + r'\w+)\s*\(', s):
        name = m.group(1)
        if name not in declared:
            problems.append('call to undeclared %s at offset %d' % (name, m.start()))
        elif declared[name] > m.start() and not decl.match(s, s.rfind('\n', 0, m.start()) + 1):
            problems.append('%s used before declaration at offset %d' % (name, m.start()))
    return problems


if __name__ == '__main__':
    import sys
    bad = 0
    for p in sys.argv[1:]:
        with open(p, encoding='utf-8-sig') as f:
            res = lint(f.read())
        for r in res:
            print('%s: %s' % (p, r))
            bad += 1
    sys.exit(1 if bad else 0)
