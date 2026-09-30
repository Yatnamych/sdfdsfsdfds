"""Парсер команд с раскрытием переменных окружения."""
import os
import re
import shlex


class ParseError(Exception):
    """Ошибка разбора командной строки."""


# Регулярка: $VAR, ${VAR}, $?, $$, $0..$9
_VAR_RE = re.compile(
    r"\$(\{[A-Za-z_][A-Za-z0-9_]*\}"
    r"|[A-Za-z_][A-Za-z0-9_]*"
    r"|\?|\$|[0-9])"
)

# Константы вместо магических чисел
_MIN_PIPELINE_LEN = 1
_PIPELINE_INDEX = 0


def expand_vars(token: str, last_status: int = 0) -> str:
    """Раскрывает переменные окружения в одном токене.

    Поддерживает $VAR, ${VAR}, $?, $$ и позиционные $0..$9.

    Args:
        token: Исходный токен.
        last_status: Код возврата предыдущей команды (для $?).

    Returns:
        Токен с раскрытыми переменными.
    """
    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name == "?":
            return str(last_status)
        if name == "$":
            return str(os.getpid())
        if name.isdigit():
            return ""
        if name.startswith("{"):
            name = name[1:-1]
        return os.environ.get(name, "")

    return _VAR_RE.sub(_replace, token)


def _tokenize(line: str) -> list[str]:
    """Разбивает строку на токены с учётом кавычек.

    Args:
        line: Строка команды.

    Returns:
        Список токенов.

    Raises:
        ParseError: Если кавычки не сбалансированы.
    """
    try:
        return shlex.split(line, posix=True)
    except ValueError as exc:
        raise ParseError(f"Ошибка разбора строки: {exc}") from exc


def _consume_redirect(
    tokens: list[str],
    index: int,
    expected: str,
) -> int:
    """Проверяет, что после оператора есть файл.

    Args:
        tokens: Список токенов.
        index: Индекс следующего токена.
        expected: Имя оператора (для сообщения об ошибке).

    Returns:
        Индекс токена с именем файла.

    Raises:
        ParseError: Если файл не указан.
    """
    if index >= len(tokens):
        raise ParseError(f"Ожидался файл после '{expected}'")
    return index


def _split_pipelines(tokens: list[str], last_status: int) -> tuple[
    list[list[str]],
    str | None,
    str | None,
    bool,
    bool,
]:
    """Разбирает токены на pipeline и редиректы.

    Args:
        tokens: Список токенов.
        last_status: Код возврата предыдущей команды.

    Returns:
        Кортеж (pipelines, redirect_in, redirect_out, append, background).

    Raises:
        ParseError: При некорректном синтаксисе.
    """
    pipelines: list[list[str]] = [[]]
    redirect_in: str | None = None
    redirect_out: str | None = None
    append = False
    background = False

    index = 0
    while index < len(tokens):
        token = expand_vars(tokens[index], last_status)

        if token == "|":
            pipelines.append([])
        elif token == ">":
            index = _consume_redirect(tokens, index + 1, ">")
            redirect_out = expand_vars(tokens[index], last_status)
            append = False
        elif token == ">>":
            index = _consume_redirect(tokens, index + 1, ">>")
            redirect_out = expand_vars(tokens[index], last_status)
            append = True
        elif token == "<":
            index = _consume_redirect(tokens, index + 1, "<")
            redirect_in = expand_vars(tokens[index], last_status)
        elif token == "&":
            background = True
        else:
            pipelines[-1].append(token)
        index += 1

    pipelines = [p for p in pipelines if p]
    if not pipelines:
        return [], None, None, False, False
    return pipelines, redirect_in, redirect_out, append, background


def parse(
    line: str,
    last_status: int = 0,
) -> tuple[list[list[str]], str | None, str | None, bool, bool] | None:
    """Разбирает строку на pipeline и редиректы.

    Поддерживает операторы: | > < >> &.

    Args:
        line: Строка команды.
        last_status: Код возврата предыдущей команды.

    Returns:
        Кортеж (pipelines, redirect_in, redirect_out, append, background)
        или None для пустой строки.
    """
    line = line.strip()
    if not line:
        return None

    tokens = _tokenize(line)
    if not tokens:
        return None

    return _split_pipelines(tokens, last_status)