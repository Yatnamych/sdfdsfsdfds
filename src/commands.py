"""Реализация команд эмулятора."""
import os
import sys
import datetime
from vfs import VFSError


class CommandError(Exception):
    pass


# ---------- вспомогательное ----------
def _fmt_size(n):
    if n < 1024:
        return f"{n}"
    for unit in ("K", "M", "G"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f}{unit}"
    return f"{n:.1f}T"


def _node_path(vfs, node):
    chain = []
    cur = node
    while cur is not vfs.root:
        chain.append(cur.name)
        cur = cur.parent
    return "/" + "/".join(reversed(chain)) if chain else "/"


# ---------- команды ----------
def cmd_ls(ctx, args):
    """ls [-l] [-a] [path]"""
    vfs = ctx.vfs
    long_fmt = False
    show_all = False
    paths = []
    for a in args:
        if a == "-l":
            long_fmt = True
        elif a == "-a":
            show_all = True
        elif a == "-la" or a == "-al":
            long_fmt = True
            show_all = True
        elif a.startswith("-"):
            raise CommandError(f"ls: неверный ключ -- '{a}'")
        else:
            paths.append(a)
    if not paths:
        paths = ["."]

    out_lines = []
    for p in paths:
        try:
            node = vfs.resolve(p)
        except VFSError as e:
            raise CommandError(f"ls: {e}")
        if node.is_dir:
            names = sorted(node.children.keys())
            if not show_all:
                names = [n for n in names if not n.startswith(".")]
            if long_fmt:
                out_lines.append(f"total {len(names)}")
                for n in names:
                    ch = node.children[n]
                    kind = "d" if ch.is_dir else "-"
                    size = len(ch.content) if not ch.is_dir else 4096
                    out_lines.append(
                        f"{kind}rw-r--r-- 1 user user {size:>8} "
                        f"{datetime.datetime.now():%b %d %H:%M} {n}")
            else:
                if len(paths) > 1:
                    out_lines.append(f"{p}:")
                out_lines.append("  ".join(names))
        else:
            out_lines.append(p)
    return "\n".join(out_lines)


def cmd_cd(ctx, args):
    """cd [path]"""
    vfs = ctx.vfs
    if len(args) > 1:
        raise CommandError("cd: слишком много аргументов")
    target = args[0] if args else os.environ.get("HOME", "/")
    try:
        node = vfs.resolve(target)
    except VFSError as e:
        raise CommandError(f"cd: {e}")
    if not node.is_dir:
        raise CommandError(f"cd: {target}: Не каталог")
    vfs.cwd = node
    return ""


def cmd_tree(ctx, args):
    """tree [-a] [path]"""
    vfs = ctx.vfs
    show_all = "-a" in args
    paths = [a for a in args if not a.startswith("-")]
    if not paths:
        paths = ["."]
    out = []
    for p in paths:
        try:
            node = vfs.resolve(p)
        except VFSError as e:
            raise CommandError(f"tree: {e}")
        out.append(p)
        out.extend(_tree_lines(node, "", show_all))
    return "\n".join(out)


def _tree_lines(node, prefix, show_all):
    if not node.is_dir:
        return
    names = sorted(node.children.keys())
    if not show_all:
        names = [n for n in names if not n.startswith(".")]
    for i, name in enumerate(names):
        last = (i == len(names) - 1)
        branch = "└── " if last else "├── "
        child = node.children[name]
        out = [prefix + branch + name]
        if child.is_dir:
            ext = "    " if last else "│   "
            out.extend(_tree_lines(child, prefix + ext, show_all))
        yield from out


def cmd_uniq(ctx, args):
    """uniq [-c] [file]  — читает stdin или файл."""
    count = False
    files = []
    for a in args:
        if a == "-c":
            count = True
        elif a.startswith("-"):
            raise CommandError(f"uniq: неверный ключ -- '{a}'")
        else:
            files.append(a)

    if files:
        try:
            node = ctx.vfs.resolve(files[0])
        except VFSError as e:
            raise CommandError(f"uniq: {e}")
        if node.is_dir:
            raise CommandError(f"uniq: {files[0]}: Это каталог")
        lines = node.content.splitlines()
    else:
        data = ctx.stdin or ""
        lines = data.splitlines()

    result = []
    prev = object()
    cnt = 0
    for ln in lines:
        if ln == prev:
            cnt += 1
        else:
            if cnt:
                result.append((cnt, prev))
            prev = ln
            cnt = 1
    if cnt:
        result.append((cnt, prev))

    if count:
        return "\n".join(f"{c:>7} {l}" for c, l in result)
    return "\n".join(l for _, l in result)


def cmd_date(ctx, args):
    """date [-u] [+FORMAT]"""
    if args and args[0].startswith("+"):
        fmt = args[0][1:]
        # грубая замена strftime-подобных токенов
        now = datetime.datetime.utcnow() if "-u" in args else datetime.datetime.now()
        # поддержка формата через strftime
        try:
            return now.strftime(fmt)
        except Exception as e:
            raise CommandError(f"date: неверный формат: {e}")
    now = datetime.datetime.utcnow() if "-u" in args else datetime.datetime.now()
    return now.strftime("%a %b %d %H:%M:%S %Z %Y")


def cmd_pwd(ctx, args):
    return _node_path(ctx.vfs, ctx.vfs.cwd)


def cmd_echo(ctx, args):
    return " ".join(args)


def cmd_cat(ctx, args):
    if not args:
        return ctx.stdin or ""
    out = []
    for f in args:
        try:
            node = ctx.vfs.resolve(f)
        except VFSError as e:
            raise CommandError(f"cat: {e}")
        if node.is_dir:
            raise CommandError(f"cat: {f}: Это каталог")
        out.append(node.content)
    return "".join(out)


def cmd_mkdir(ctx, args):
    if not args:
        raise CommandError("mkdir: не указан операнд")
    for p in args:
        try:
            ctx.vfs.mkdir(p)
        except VFSError as e:
            raise CommandError(f"mkdir: {e}")
    return ""


def cmd_rmdir(ctx, args):
    if not args:
        raise CommandError("rmdir: не указан операнд")
    for p in args:
        try:
            ctx.vfs.rmdir(p)
        except VFSError as e:
            raise CommandError(f"rmdir: {e}")
    return ""


def cmd_touch(ctx, args):
    if not args:
        raise CommandError("touch: не указан операнд")
    for p in args:
        try:
            ctx.vfs.create_file(p, "")
        except VFSError as e:
            raise CommandError(f"touch: {e}")
    return ""


def cmd_exit(ctx, args):
    raise SystemExit(0)


def cmd_help(ctx, args):
    return (
        "Доступные команды:\n"
        "  ls [-l] [-a] [path]     — список файлов\n"
        "  cd [path]               — сменить каталог\n"
        "  pwd                     — текущий каталог\n"
        "  tree [-a] [path]        — дерево каталогов\n"
        "  cat file...             — вывести содержимое\n"
        "  echo args...            — вывести аргументы\n"
        "  uniq [-c] [file]        — уникальные строки\n"
        "  date [-u] [+FORMAT]     — дата/время\n"
        "  mkdir dir...            — создать каталог\n"
        "  rmdir dir...            — удалить пустой каталог\n"
        "  touch file...           — создать пустой файл\n"
        "  help                    — эта справка\n"
        "  exit                    — выход"
    )


COMMANDS = {
    "ls": cmd_ls,
    "cd": cmd_cd,
    "pwd": cmd_pwd,
    "tree": cmd_tree,
    "cat": cmd_cat,
    "echo": cmd_echo,
    "uniq": cmd_uniq,
    "date": cmd_date,
    "mkdir": cmd_mkdir,
    "rmdir": cmd_rmdir,
    "touch": cmd_touch,
    "help": cmd_help,
    "exit": cmd_exit,
}


class Context:
    def __init__(self, vfs, stdin=None):
        self.vfs = vfs
        self.stdin = stdin