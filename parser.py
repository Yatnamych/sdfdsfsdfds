"""Парсер команд с раскрытием переменных окружения."""
import os
import re
import shlex


class ParseError(Exception):
    pass


# Регулярка: $VAR, ${VAR}, $?, $$, $0..$9
_VAR_RE = re.compile(r"""
    \$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*|\?|\$|[0-9])
""", re.VERBOSE)


def expand_vars(token: str, last_status: int = 0) -> str:
    """Раскрывает переменные окружения в одном токене."""
    def repl(m):
        name = m.group(1)
        if name == "?":
            return str(last_status)
        if name == "$":
            return str(os.getpid())
        if name.isdigit():
            return ""
        if name.startswith("{"):
            name = name[1:-1]
        return os.environ.get(name, "")
    return _VAR_RE.sub(repl, token)


def parse(line: str, last_status: int = 0):
    """
    Разбирает строку на (pipeline, redirect_out, redirect_in, background).
    Поддерживает: | > < >> &
    """
    line = line.strip()
    if not line:
        return None

    # Разделители — не внутри кавычек
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError as e:
        raise ParseError(f"Ошибка разбора строки: {e}")

    if not tokens:
        return None

    # Раскрытие переменных
    tokens = [expand_vars(t, last_status) for t in tokens]

    # Разбор pipeline и редиректов
    pipelines = [[]]
    redirect_out = None
    redirect_in = None
    append = False
    background = False

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "|":
            pipelines.append([])
        elif t == ">":
            i += 1
            if i >= len(tokens):
                raise ParseError("Ожидался файл после '>'")
            redirect_out = tokens[i]
            append = False
        elif t == ">>":
            i += 1
            if i >= len(tokens):
                raise ParseError("Ожидался файл после '>>'")
            redirect_out = tokens[i]
            append = True
        elif t == "<":
            i += 1
            if i >= len(tokens):
                raise ParseError("Ожидался файл после '<'")
            redirect_in = tokens[i]
        elif t == "&":
            background = True
        else:
            pipelines[-1].append(t)
        i += 1

    pipelines = [p for p in pipelines if p]
    if not pipelines:
        return None
    return pipelines, redirect_in, redirect_out, append, background