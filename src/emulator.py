#!/usr/bin/env python3
"""Эмулятор shell для UNIX-подобной ОС."""
import argparse
import getpass
import os
import socket
import sys

from .commands import COMMANDS, CommandError, Context
from .parser import ParseError, parse
from .vfs import VFS, VFSError


# Константы вместо магических чисел
_STATUS_OK = 0
_STATUS_ERROR = 1
_STATUS_NOT_FOUND = 127
_STATUS_INTERRUPT = 130
_EXIT_VFS_ERROR = 2
_INDEX_COMMAND = 0


def build_prompt(template: str | None = None) -> str:
    """Формирует приглашение к вводу.

    Args:
        template: Пользовательский шаблон приглашения.

    Returns:
        Строка приглашения.
    """
    if template:
        return template
    user = os.environ.get("USER") or getpass.getuser()
    host = socket.gethostname().split(".")[_INDEX_COMMAND]
    home = os.environ.get("HOME", "/")
    cwd = os.getcwd()
    if cwd.startswith(home):
        disp = "~" + cwd[len(home):]
    else:
        disp = cwd
    return f"{user}@{host}:{disp}$ "


def _apply_redirect_in(ctx: Context, path: str) -> str | None:
    """Читает данные для stdin из файла.

    Args:
        ctx: Контекст.
        path: Путь к файлу.

    Returns:
        Содержимое файла.
    """
    node = ctx.vfs.resolve(path)
    return node.content


def _execute_pipeline(
    ctx: Context,
    pipelines: list[list[str]],
    stdin_data: str | None,
    last_status: int,
) -> tuple[int, str]:
    """Выполняет конвейер команд.

    Args:
        ctx: Контекст.
        pipelines: Список команд.
        stdin_data: Входные данные.
        last_status: Код возврата предыдущей команды.

    Returns:
        Кортеж (status, output).
    """
    out_buffer = stdin_data or ""
    status = last_status
    for index, tokens in enumerate(pipelines):
        name = tokens[_INDEX_COMMAND]
        args = tokens[1:]
        if name not in COMMANDS:
            return _STATUS_NOT_FOUND, f"{name}: команда не найдена"
        ctx.stdin = (
            out_buffer
            if index > 0 or stdin_data is not None
            else None
        )
        try:
            result = COMMANDS[name](ctx, args)
            out_buffer = result if result is not None else ""
            status = _STATUS_OK
        except CommandError as exc:
            return _STATUS_ERROR, str(exc)
        except VFSError as exc:
            return _STATUS_ERROR, str(exc)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            return _STATUS_ERROR, f"{name}: внутренняя ошибка: {exc}"
    return status, out_buffer


def _write_redirect_out(
    ctx: Context,
    path: str,
    data: str,
    append: bool,
) -> str | None:
    """Записывает вывод в файл.

    Args:
        ctx: Контекст.
        path: Путь файла.
        data: Данные.
        append: Режим дозаписи.

    Returns:
        Сообщение об ошибке или None.
    """
    payload = data + ("\n" if data else "")
    try:
        node = ctx.vfs.resolve(path)
        if node.is_dir:
            return f"{path}: Это каталог"
        if append:
            node.content += payload
        else:
            node.content = payload
    except VFSError:
        try:
            ctx.vfs.create_file(path, payload)
        except VFSError as exc:
            return f"Ошибка перенаправления вывода: {exc}"
    return None


def run_command_line(
    ctx: Context,
    line: str,
    last_status: int = 0,
    echo: bool = False,
) -> tuple[int, str]:
    """Выполняет одну строку команды.

    Args:
        ctx: Контекст.
        line: Строка команды.
        last_status: Код возврата предыдущей команды.
        echo: Не используется (для совместимости).

    Returns:
        Кортеж (status, output).
    """
    parsed = parse(line, last_status)
    if parsed is None:
        return last_status, ""
    pipelines, redirect_in, redirect_out, append, _ = parsed

    stdin_data: str | None = None
    if redirect_in:
        try:
            stdin_data = _apply_redirect_in(ctx, redirect_in)
        except VFSError as exc:
            return _STATUS_ERROR, f"Ошибка перенаправления ввода: {exc}"

    status, out_buffer = _execute_pipeline(
        ctx, pipelines, stdin_data, last_status
    )

    if redirect_out:
        error = _write_redirect_out(ctx, redirect_out, out_buffer, append)
        if error:
            return _STATUS_ERROR, error
        out_buffer = ""

    return status, out_buffer


def _print_script_line(line: str, echo: bool) -> None:
    """Печатает строку скрипта при включённом echo.

    Args:
        line: Строка скрипта.
        echo: Флаг вывода.
    """
    if echo:
        print(f"$ {line}")


def run_script(ctx: Context, path: str, echo: bool = True) -> None:
    """Выполняет стартовый скрипт.

    Args:
        ctx: Контекст.
        path: Путь к скрипту.
        echo: Печатать ли строки скрипта.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError as exc:
        print(f"Ошибка чтения скрипта: {exc}", file=sys.stderr)
        return

    last = _STATUS_OK
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            _print_script_line(line, echo)
            continue
        _print_script_line(line, echo)
        try:
            last, out = run_command_line(ctx, line, last)
            if out:
                print(out)
        except SystemExit:
            print("Выход из скрипта")
            return


def repl(ctx: Context, prompt_template: str | None) -> None:
    """Запускает главный цикл REPL.

    Args:
        ctx: Контекст.
        prompt_template: Шаблон приглашения.
    """
    last = _STATUS_OK
    while True:
        try:
            line = input(build_prompt(prompt_template))
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("^C")
            last = _STATUS_INTERRUPT
            continue
        try:
            last, out = run_command_line(ctx, line, last)
            if out:
                print(out)
        except SystemExit:
            break


def _print_debug(args: argparse.Namespace) -> None:
    """Печатает отладочную информацию о параметрах запуска.

    Args:
        args: Разобранные аргументы командной строки.
    """
    print("=== Параметры запуска эмулятора ===")
    print(f"  VFS:           {args.vfs or '(не задан, пустая VFS)'}")
    print(
        f"  Prompt:        "
        f"{args.prompt or '(по умолчанию, из реальной ОС)'}"
    )
    print(f"  Script:        {args.script or '(не задан)'}")
    print(
        f"  USER={os.environ.get('USER', '?')}  "
        f"HOME={os.environ.get('HOME', '?')}  "
        f"HOST={socket.gethostname()}"
    )
    print("===================================")


def _build_arg_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки.

    Returns:
        Настроенный ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Эмулятор shell UNIX-подобной ОС (VFS + скрипты)."
    )
    parser.add_argument(
        "--vfs",
        default=None,
        help="Путь к XML-файлу виртуальной файловой системы",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Шаблон приглашения (например 'user@host:~$ ')",
    )
    parser.add_argument(
        "--script",
        default=None,
        help="Путь к стартовому скрипту",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Отладочный вывод параметров запуска",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Не входить в REPL после скрипта",
    )
    return parser


def _load_vfs(path: str | None) -> VFS:
    """Загружает VFS из файла или создаёт пустую.

    Args:
        path: Путь к XML или None.

    Returns:
        VFS.
    """
    if not path:
        return VFS()
    try:
        return VFS.from_xml(path)
    except (OSError, et_parse_error()) as exc:
        print(f"Ошибка загрузки VFS: {exc}", file=sys.stderr)
        sys.exit(_EXIT_VFS_ERROR)


def et_parse_error() -> type[Exception]:
    """Возвращает тип ошибки XML-парсера.

    Returns:
        Класс исключения для ошибок XML.
    """
    import xml.etree.ElementTree as et
    return et.ParseError


def main() -> None:
    """Точка входа эмулятора."""
    args = _build_arg_parser().parse_args()

    if args.debug or args.script:
        _print_debug(args)

    vfs = _load_vfs(args.vfs)
    ctx = Context(vfs)

    if args.script:
        run_script(ctx, args.script, echo=True)
        if args.no_interactive:
            return

    repl(ctx, args.prompt)


if __name__ == "__main__":
    main()