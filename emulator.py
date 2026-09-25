#!/usr/bin/env python3
"""Эмулятор shell для UNIX-подобной ОС."""
import argparse
import getpass
import os
import socket
import sys

from parser import parse, ParseError
from vfs import VFS, VFSError
import commands as C


def build_prompt(template=None):
    if template:
        return template
    user = os.environ.get("USER") or getpass.getuser()
    host = socket.gethostname().split(".")[0]
    home = os.environ.get("HOME", "/")
    cwd = os.getcwd()
    if cwd.startswith(home):
        disp = "~" + cwd[len(home):]
    else:
        disp = cwd
    return f"{user}@{host}:{disp}$ "


def run_command_line(ctx, line, last_status=0, echo=False):
    """Выполняет одну строку. Возвращает (status, output)."""
    parsed = parse(line, last_status)
    if parsed is None:
        return last_status, ""
    pipelines, redirect_in, redirect_out, append, background = parsed

    stdin_data = None
    if redirect_in:
        try:
            node = ctx.vfs.resolve(redirect_in)
            stdin_data = node.content
        except VFSError as e:
            return 1, f"Ошибка перенаправления ввода: {e}"

    # Выполняем конвейер последовательно (упрощённо, но с передачей stdin)
    out_buffer = stdin_data or ""
    status = last_status

    for i, tokens in enumerate(pipelines):
        name = tokens[0]
        args = tokens[1:]

        if name not in C.COMMANDS:
            out_buffer = f"{name}: команда не найдена"
            status = 127
            break

        ctx.stdin = out_buffer if i > 0 or stdin_data is not None else None
        try:
            result = C.COMMANDS[name](ctx, args)
            out_buffer = result if result is not None else ""
            status = 0
        except C.CommandError as e:
            out_buffer = str(e)
            status = 1
        except VFSError as e:
            out_buffer = str(e)
            status = 1
        except SystemExit:
            raise
        except Exception as e:
            out_buffer = f"{name}: внутренняя ошибка: {e}"
            status = 1

    # Перенаправление вывода
    if redirect_out:
        try:
            mode = "a" if append else "w"
            try:
                node = ctx.vfs.resolve(redirect_out)
                if node.is_dir:
                    return 1, f"{redirect_out}: Это каталог"
                if append:
                    node.content += out_buffer + "\n"
                else:
                    node.content = out_buffer + ("\n" if out_buffer else "")
            except VFSError:
                ctx.vfs.create_file(redirect_out, out_buffer + ("\n" if out_buffer else ""))
        except VFSError as e:
            return 1, f"Ошибка перенаправления вывода: {e}"
        out_buffer = ""

    return status, out_buffer


def run_script(ctx, path, echo=True):
    """Выполняет стартовый скрипт, имитируя диалог."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"Ошибка чтения скрипта: {e}", file=sys.stderr)
        return

    last = 0
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        # комментарии: # ...  (синтаксис Python)
        if not stripped or stripped.startswith("#"):
            if echo and stripped.startswith("#"):
                print(f"$ {line}")
            continue
        if echo:
            print(f"$ {line}")
        try:
            last, out = run_command_line(ctx, line, last)
            if out:
                print(out)
        except SystemExit:
            print("Выход из скрипта")
            return


def repl(ctx, prompt_template):
    last = 0
    while True:
        try:
            line = input(build_prompt(prompt_template))
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("^C")
            last = 130
            continue
        try:
            last, out = run_command_line(ctx, line, last)
            if out:
                print(out)
        except SystemExit:
            break


def main():
    ap = argparse.ArgumentParser(
        description="Эмулятор shell UNIX-подобной ОС (VFS + скрипты).")
    ap.add_argument("--vfs", default=None,
                    help="Путь к XML-файлу виртуальной файловой системы")
    ap.add_argument("--prompt", default=None,
                    help="Шаблон приглашения (например 'user@host:~$ ')")
    ap.add_argument("--script", default=None,
                    help="Путь к стартовому скрипту")
    ap.add_argument("--debug", action="store_true",
                    help="Отладочный вывод параметров запуска")
    ap.add_argument("--no-interactive", action="store_true",
                    help="Не входить в REPL после скрипта")
    args = ap.parse_args()

    # ---- Этап 2: отладочный вывод параметров ----
    if args.debug or args.script:
        print("=== Параметры запуска эмулятора ===")
        print(f"  VFS:           {args.vfs or '(не задан, пустая VFS)'}")
        print(f"  Prompt:        {args.prompt or '(по умолчанию, из реальной ОС)'}")
        print(f"  Script:        {args.script or '(не задан)'}")
        print(f"  USER={os.environ.get('USER','?')}  HOME={os.environ.get('HOME','?')}  "
              f"HOST={socket.gethostname()}")
        print("===================================")

    # ---- VFS ----
    if args.vfs:
        try:
            vfs = VFS.from_xml(args.vfs)
        except Exception as e:
            print(f"Ошибка загрузки VFS: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        vfs = VFS()

    ctx = C.Context(vfs)

    # ---- стартовый скрипт ----
    if args.script:
        run_script(ctx, args.script, echo=True)
        if args.no_interactive:
            return

    # ---- REPL ----
    repl(ctx, args.prompt)


if __name__ == "__main__":
    main()