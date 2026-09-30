"""Виртуальная файловая система, загружаемая из XML в память."""
import base64
import xml.etree.ElementTree as et


class VFSError(Exception):
    """Ошибка виртуальной файловой системы."""


class Node:
    """Узел виртуальной файловой системы (файл или каталог)."""

    def __init__(
        self,
        name: str,
        is_dir: bool = False,
        content: str = "",
        binary: bool = False,
        mode: str = "0644",
    ) -> None:
        """Инициализация узла.

        Args:
            name: Имя узла.
            is_dir: True, если это каталог.
            content: Содержимое (для файла).
            binary: True, если содержимое было в base64.
            mode: Права доступа.
        """
        self.name = name
        self.is_dir = is_dir
        self.content = content
        self.binary = binary
        self.mode = mode
        self.children: dict[str, "Node"] = {}
        self.parent: "Node | None" = None


# Константы вместо магических чисел
_ROOT_MODE = "0755"
_DIR_MODE = "0755"
_FILE_MODE = "0644"


class VFS:
    """Виртуальная файловая система в памяти."""

    def __init__(self) -> None:
        """Создаёт пустую VFS с корневым каталогом."""
        self.root = Node("/", is_dir=True, mode=_ROOT_MODE)
        self.root.parent = self.root
        self.cwd = self.root

    # -------- работа с путями --------
    def _split(self, path: str) -> tuple[Node, list[str]]:
        """Разбивает путь на стартовый узел и компоненты.

        Args:
            path: Абсолютный или относительный путь.

        Returns:
            Кортеж (стартовый узел, список компонентов).
        """
        if path.startswith("/"):
            node = self.root
        else:
            node = self.cwd
        parts = [p for p in path.split("/") if p]
        return node, parts

    def resolve(self, path: str, must_exist: bool = True) -> Node | None:
        """Разрешает путь в узел VFS.

        Args:
            path: Путь.
            must_exist: Если True — бросает VFSError при отсутствии.

        Returns:
            Найденный узел или None.

        Raises:
            VFSError: Если путь не существует и must_exist=True.
        """
        node, parts = self._split(path)
        for part in parts:
            if part in (".", ""):
                continue
            if part == "..":
                node = node.parent
                continue
            if not node.is_dir or part not in node.children:
                if must_exist:
                    raise VFSError(
                        f"{path}: Нет такого файла или каталога"
                    )
                return None
            node = node.children[part]
        return node

    def _node_abspath(self, node: Node) -> str:
        """Строит абсолютный путь до узла.

        Args:
            node: Узел VFS.

        Returns:
            Абсолютный путь.
        """
        chain: list[str] = []
        cur = node
        while cur is not self.root:
            chain.append(cur.name)
            cur = cur.parent
        return "/" + "/".join(reversed(chain)) if chain else "/"

    def abspath(self, path: str) -> str:
        """Возвращает канонический абсолютный путь.

        Args:
            path: Путь.

        Returns:
            Абсолютный путь.
        """
        node = self.resolve(path)
        assert node is not None
        return self._node_abspath(node)

    # -------- операции --------
    def _parent_and_name(self, path: str) -> tuple[Node, str]:
        """Возвращает родительский узел и имя последнего компонента.

        Args:
            path: Путь.

        Returns:
            Кортеж (родитель, имя).

        Raises:
            VFSError: Если родителя нет или имя пустое.
        """
        node, parts = self._split(path)
        for part in parts[:-1]:
            if part == "..":
                node = node.parent
                continue
            if part not in node.children:
                raise VFSError(f"{path}: Нет такого файла или каталога")
            node = node.children[part]
        if not parts:
            raise VFSError("Не указано имя")
        return node, parts[-1]

    def mkdir(self, path: str) -> Node:
        """Создаёт каталог.

        Args:
            path: Путь нового каталога.

        Returns:
            Созданный узел.

        Raises:
            VFSError: Если каталог уже существует или нет родителя.
        """
        parent, name = self._parent_and_name(path)
        if name in parent.children:
            raise VFSError(
                f"mkdir: невозможно создать каталог '{name}': "
                f"Файл существует"
            )
        new = Node(name, is_dir=True, mode=_DIR_MODE)
        new.parent = parent
        parent.children[name] = new
        return new

    def rmdir(self, path: str) -> None:
        """Удаляет пустой каталог.

        Args:
            path: Путь каталога.

        Raises:
            VFSError: Если это не каталог, каталог не пуст или это корень.
        """
        node = self.resolve(path)
        assert node is not None
        if not node.is_dir:
            raise VFSError(f"rmdir: '{path}': Не каталог")
        if node is self.root:
            raise VFSError("rmdir: нельзя удалить корень")
        if node.children:
            raise VFSError(
                f"rmdir: не удалось удалить '{path}': Каталог не пуст"
            )
        del node.parent.children[node.name]

    def create_file(
        self,
        path: str,
        content: str = "",
        binary: bool = False,
    ) -> Node:
        """Создаёт или перезаписывает файл.

        Args:
            path: Путь файла.
            content: Содержимое.
            binary: Флаг бинарного содержимого.

        Returns:
            Созданный или обновлённый узел.
        """
        parent, name = self._parent_and_name(path)
        if name in parent.children:
            parent.children[name].content = content
            return parent.children[name]
        new = Node(name, is_dir=False, content=content,
                   binary=binary, mode=_FILE_MODE)
        new.parent = parent
        parent.children[name] = new
        return new

    # -------- загрузка из XML --------
    @classmethod
    def from_xml(cls, xml_path: str) -> "VFS":
        """Загружает VFS из XML-файла.

        Args:
            xml_path: Путь к XML-файлу.

        Returns:
            Загруженная VFS.
        """
        tree = et.parse(xml_path)
        root_el = tree.getroot()
        vfs = cls()
        vfs._build_from_element(root_el, vfs.root)
        return vfs

    def _build_from_element(self, element, parent: Node) -> None:
        """Рекурсивно строит VFS из XML-элемента.

        Args:
            element: XML-элемент.
            parent: Родительский узел.
        """
        for child in element:
            if child.tag not in ("dir", "file"):
                continue
            name = child.get("name")
            if child.tag == "dir":
                node = Node(name, is_dir=True, mode=_DIR_MODE)
                node.parent = parent
                parent.children[name] = node
                self._build_from_element(child, node)
            else:
                node = self._make_file_node(child, name, parent)
                parent.children[name] = node

    @staticmethod
    def _make_file_node(element, name: str, parent: Node) -> Node:
        """Создаёт узел файла из XML-элемента.

        Args:
            element: XML-элемент файла.
            name: Имя файла.
            parent: Родительский узел.

        Returns:
            Узел файла.
        """
        binary = element.get("encoding") == "base64"
        text = element.text or ""
        if binary:
            try:
                text = base64.b64decode(text.strip()).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, base64.binascii.Error):
                text = "<binary>"
        node = Node(name, is_dir=False, content=text,
                    binary=binary, mode=_FILE_MODE)
        node.parent = parent
        return node