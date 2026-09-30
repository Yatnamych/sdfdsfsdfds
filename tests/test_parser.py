"""Тесты для модуля parser."""
import pytest

from src.parser import ParseError, expand_vars, parse


class TestExpandVars:
    """Тесты раскрытия переменных окружения."""

    def test_expand_simple_var(self, monkeypatch):
        """$HOME подставляется из окружения."""
        monkeypatch.setenv("HOME", "/home/user")
        assert expand_vars("$HOME") == "/home/user"

    def test_expand_braced_var(self, monkeypatch):
        """${USER} раскрывается."""
        monkeypatch.setenv("USER", "alice")
        assert expand_vars("${USER}") == "alice"

    def test_expand_unknown_var(self):
        """Неизвестная переменная заменяется пустой строкой."""
        assert expand_vars("$UNKNOWN_XYZ_123") == ""

    def test_expand_status(self):
        """$? подставляет код возврата."""
        assert expand_vars("$?", 42) == "42"

    def test_expand_with_text(self, monkeypatch):
        """Переменная внутри текста раскрывается."""
        monkeypatch.setenv("USER", "bob")
        assert expand_vars("hi $USER!") == "hi bob!"


class TestParse:
    """Тесты разбора командной строки."""

    def test_empty_line(self):
        """Пустая строка — None."""
        assert parse("") is None
        assert parse("   ") is None

    def test_simple_command(self):
        """Одна команда без операторов."""
        result = parse("ls -la")
        assert result is not None
        pipelines, rin, rout, append, bg = result
        assert pipelines == [["ls", "-la"]]
        assert rin is None and rout is None
        assert append is False and bg is False

    def test_pipe(self):
        """Конвейер из двух команд."""
        pipelines, *_ = parse("cat file | uniq")
        assert pipelines == [["cat", "file"], ["uniq"]]

    def test_redirect_out(self):
        """Перенаправление вывода >."""
        pipelines, _, rout, append, _ = parse("ls > out.txt")
        assert pipelines == [["ls"]]
        assert rout == "out.txt"
        assert append is False

    def test_redirect_append(self):
        """Перенаправление >>."""
        _, _, rout, append, _ = parse("ls >> out.txt")
        assert rout == "out.txt"
        assert append is True

    def test_redirect_in(self):
        """Перенаправление ввода <."""
        _, rin, _, _, _ = parse("cat < in.txt")
        assert rin == "in.txt"

    def test_background(self):
        """Фоновый режим &."""
        *_, bg = parse("sleep &")
        assert bg is True

    def test_error_after_redirect(self):
        """Ошибка при отсутствии файла после >."""
        with pytest.raises(ParseError):
            parse("ls >")

    def test_unbalanced_quotes(self):
        """Ошибка при несбалансированных кавычках."""
        with pytest.raises(ParseError):
            parse("echo 'unterminated")