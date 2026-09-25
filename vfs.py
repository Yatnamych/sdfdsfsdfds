"""Виртуальная файловая система, загружаемая из XML в память."""
import base64
import xml.etree.ElementTree as ET


class VFSError(Exception):
    pass


class Node:
    def __init__(self, name, is_dir=False, content="", binary=False, mode="0644"):
        self.name = name
        self.is_dir = is_dir
        self.content = content  # str
        self.binary = binary
        self.mode = mode
        self.children = {}   # name -> Node (для каталогов)
        self.parent = None


class VFS:
    def __init__(self):
        self.root = Node("/", is_dir=True)
        self.root.parent = self.root
        self.cwd = self.root

    # -------- работа с путями --------
    def _split(self, path):
        if path.startswith("/"):
            node = self.root
            parts = [p for p in path.split("/") if p]
        else:
            node = self.cwd
            parts = [p for p in path.split("/") if p]
        return node, parts

    def resolve(self, path, must_exist=True):
        node, parts = self._split(path)
        for p in parts:
            if p == "." or p == "":
                continue
            if p == "..":
                node = node.parent
                continue
            if not node.is_dir or p not in node.children:
                if must_exist:
                    raise VFSError(f"{path}: Нет такого файла или каталога")
                return None
            node = node.children[p]
        return node

    def abspath(self, path):
        """Возвращает канонический абсолютный путь."""
        node, parts = self._split(path)
        for p in parts:
            if p in ("", "."):
                continue
            if p == "..":
                node = node.parent
                continue
            if not node.is_dir or p not in node.children:
                raise VFSError(f"{path}: Нет такого файла или каталога")
            node = node.children[p]
        # строим путь
        chain = []
        cur = node
        while cur is not self.root:
            chain.append(cur.name)
            cur = cur.parent
        return "/" + "/".join(reversed(chain)) if chain else "/"

    # -------- операции --------
    def mkdir(self, path):
        node, parts = self._split(path)
        for p in parts[:-1]:
            if p == "..":
                node = node.parent
                continue
            if p not in node.children:
                raise VFSError(f"{path}: Нет такого файла или каталога")
            node = node.children[p]
        name = parts[-1] if parts else None
        if not name:
            raise VFSError("mkdir: не указано имя")
        if name in node.children:
            raise VFSError(f"mkdir: невозможно создать каталог '{name}': Файл существует")
        new = Node(name, is_dir=True)
        new.parent = node
        node.children[name] = new
        return new

    def rmdir(self, path):
        node = self.resolve(path)
        if not node.is_dir:
            raise VFSError(f"rmdir: '{path}': Не каталог")
        if node is self.root:
            raise VFSError("rmdir: нельзя удалить корень")
        if node.children:
            raise VFSError(f"rmdir: не удалось удалить '{path}': Каталог не пуст")
        del node.parent.children[node.name]

    def create_file(self, path, content="", binary=False):
        node, parts = self._split(path)
        for p in parts[:-1]:
            if p == "..":
                node = node.parent
                continue
            if p not in node.children:
                raise VFSError(f"{path}: Нет такого файла или каталога")
            node = node.children[p]
        if not parts:
            raise VFSError("Неверное имя файла")
        name = parts[-1]
        if name in node.children:
            node.children[name].content = content
            return node.children[name]
        new = Node(name, is_dir=False, content=content, binary=binary)
        new.parent = node
        node.children[name] = new
        return new

    # -------- обход --------
    def walk(self, node=None, prefix=""):
        """Генератор (путь, node)."""
        if node is None:
            node = self.cwd
        if node.is_dir:
            for name in sorted(node.children):
                child = node.children[name]
                path = prefix + "/" + name if prefix != "/" else "/" + name
                yield path, child
                if child.is_dir:
                    yield from self.walk(child, path)

    # -------- загрузка из XML --------
    @classmethod
    def from_xml(cls, xml_path):
        tree = ET.parse(xml_path)
        root_el = tree.getroot()
        vfs = cls()

        def build(el, parent):
            for child in el:
                if child.tag not in ("dir", "file"):
                    continue
                name = child.get("name")
                if child.tag == "dir":
                    n = Node(name, is_dir=True)
                    n.parent = parent
                    parent.children[name] = n
                    build(child, n)
                else:
                    binary = child.get("encoding") == "base64"
                    text = child.text or ""
                    if binary:
                        try:
                            text = base64.b64decode(text.strip()).decode(
                                "utf-8", errors="replace")
                        except Exception:
                            text = "<binary>"
                    n = Node(name, is_dir=False, content=text, binary=binary)
                    n.parent = parent
                    parent.children[name] = n

        build(root_el, vfs.root)
        return vfs