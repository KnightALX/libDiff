"""Windows-safe Liberty (.lib) parser.

Adapted from libertyParser (GPL-2.0) by yanqing.li / liyanqing1987.
Changes vs upstream:
- No sys.exit; raise ParseError
- Pure Python (no grep/awk/os.system)
- UTF-8 file I/O
- Fixed bus filter NameError (bundleName -> busName)
- Mutable default args fixed (None)
- Optional parse cache by absolute path
- Tolerate trailing /* */ and // comments after { / ; / }
- Group lines may use cell(name) without space before '('
- Same-line closing braces after attributes (e.g. ``index_1 (...) ; }``)
- Guard against indexing with no open group (ParseError + line number)
"""

from __future__ import annotations

import collections
import datetime
import fnmatch
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from libdiff.errors import ParseError

# Module-level parse cache: abs_path -> LibertyParser
_PARSE_CACHE: Dict[str, "LibertyParser"] = {}

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/")
_LINE_COMMENT_RE = re.compile(r"//.*?$")


def clear_parse_cache() -> None:
    _PARSE_CACHE.clear()


def _strip_quotes(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    v = value.strip()
    if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
        return v[1:-1]
    return v


def safe_float(value: Any) -> Optional[float]:
    """Convert Liberty scalar to float; missing/invalid -> None (never 0)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.upper() in {"N/A", "NA", "NONE"}:
        return None
    s = _strip_quotes(s)
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _strip_line_comments(line: str) -> str:
    """Remove /* ... */ and // comments so trailing noise does not break matchers."""
    s = _BLOCK_COMMENT_RE.sub("", line)
    s = _LINE_COMMENT_RE.sub("", s)
    return s


def _split_statements(piece: str) -> List[str]:
    """Split a brace-free piece on ';' outside quotes into statement units."""
    s = piece.strip()
    if not s or s == "}" or s.endswith("{"):
        return [s] if s else []
    parts: List[str] = []
    buf: List[str] = []
    in_string = False
    string_char = ""
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if in_string:
            buf.append(ch)
            if ch == string_char:
                bs = 0
                j = i - 1
                while j >= 0 and s[j] == '\\':
                    bs += 1
                    j -= 1
                if bs % 2 == 0:
                    in_string = False
            i += 1
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            buf.append(";")
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _flatten_liberty_line(line: str) -> List[str]:
    """Split one physical line into structural statements at { / }.

    Respects quoted strings so braces inside values are kept.
    When ``{`` appears after prior statements on the same line, those
    statements are emitted first (e.g. attr; group (name) { ... }).
    """
    s = _strip_line_comments(line).rstrip('\r\n')
    if not s.strip():
        return []
    pieces: List[str] = []
    buf: List[str] = []
    in_string = False
    string_char = ""
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if in_string:
            buf.append(ch)
            if ch == string_char:
                bs = 0
                j = i - 1
                while j >= 0 and s[j] == '\\':
                    bs += 1
                    j -= 1
                if bs % 2 == 0:
                    in_string = False
            i += 1
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "{":
            pre = "".join(buf).strip()
            buf = []
            if pre:
                stmts = _split_statements(pre)
                for stmt in stmts[:-1]:
                    pieces.append(stmt)
                last = stmts[-1] if stmts else ""
                pieces.append((last + " {").strip() if last else "{")
            else:
                pieces.append("{")
            i += 1
            continue
        if ch == "}":
            piece = "".join(buf).strip()
            buf = []
            if piece:
                for stmt in _split_statements(piece):
                    pieces.append(stmt)
            pieces.append("}")
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        for stmt in _split_statements(tail):
            pieces.append(stmt)
    return pieces


class LibertyParser:
    """Parse a Liberty file into a nested dict and expose accessors."""

    def __init__(
        self,
        lib_file: Union[str, os.PathLike],
        cell_list: Optional[Sequence[str]] = None,
        debug: bool = False,
        use_cache: bool = True,
    ):
        self.debug = debug
        path = os.path.abspath(os.fspath(lib_file))
        self.lib_path = path
        self.debug_print("* Liberty File : " + path)

        if not os.path.exists(path):
            raise ParseError('liberty file "%s": No such file!' % path)

        cell_list = list(cell_list) if cell_list else []

        if use_cache and not cell_list and path in _PARSE_CACHE:
            cached = _PARSE_CACHE[path]
            self.libDic = cached.libDic
            self._source_path = cached._source_path
            return

        source = path
        if cell_list:
            self.debug_print("* Specified Cell List : " + str(cell_list))
            source = self._filter_cells_to_temp(path, cell_list)

        group_list = self._parse_file(source)
        if not group_list:
            raise ParseError('liberty file "%s": empty or unparseable' % path)
        self.libDic = self._organize_data(group_list)
        self._source_path = source

        if use_cache and not cell_list:
            _PARSE_CACHE[path] = self

    # --- debug ---
    def debug_print(self, message: str) -> None:
        if self.debug:
            current = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print("DEBUG [" + current + "]: " + str(message))

    # compatibility aliases used by legacy callers
    def debugPrint(self, message: str) -> None:
        self.debug_print(message)

    # --- pure-Python cell filter (replaces grep/awk) ---
    def _filter_cells_to_temp(self, lib_file: str, cell_list: Sequence[str]) -> str:
        """Build a temp .lib containing library header + selected cells only."""
        cell_set = set(cell_list)
        # Allow no space before '(' and optional trailing comment after '{'
        cell_re = re.compile(r"^\s*cell\s*\((.*)\)\s*\{")

        with open(lib_file, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()

        # Find cell start line indices (0-based) and names
        cell_starts: List[tuple] = []  # (line_idx, name)
        for i, line in enumerate(lines):
            cleaned = _strip_line_comments(line)
            m = cell_re.match(cleaned)
            if m:
                cell_starts.append((i, m.group(1).strip()))

        found = {name for _, name in cell_starts}
        missing = [c for c in cell_list if c not in found]
        if missing:
            raise ParseError(
                'cells missing from "%s": %s' % (lib_file, ", ".join(missing))
            )

        # Header = everything before first cell
        first_cell_line = cell_starts[0][0] if cell_starts else len(lines)
        header = lines[:first_cell_line]

        # Map name -> (start, end exclusive)
        spans = {}
        for idx, (start, name) in enumerate(cell_starts):
            if idx + 1 < len(cell_starts):
                spans[name] = (start, cell_starts[idx + 1][0])
            else:
                # walk from start tracking brace depth to find cell end
                depth = 0
                end = start
                for j in range(start, len(lines)):
                    depth += lines[j].count("{") - lines[j].count("}")
                    end = j + 1
                    if j > start and depth <= 0:
                        break
                spans[name] = (start, end)

        out_name = lib_file + "." + "_".join(cell_list)
        with open(out_name, "w", encoding="utf-8", newline="\n") as out:
            out.writelines(header)
            for cell in cell_list:
                s, e = spans[cell]
                out.writelines(lines[s:e])
            out.write("}\n")
        self.debug_print('>>> Generated cell-based liberty file "%s"' % out_name)
        return out_name

    def genCellLibFile(self, libFile, cellList):
        """Legacy API name."""
        return self._filter_cells_to_temp(libFile, cellList)

    def getLastOpenedGroupNum(self, openedGroupNumList):
        if openedGroupNumList:
            return openedGroupNumList[-1]
        return -1

    def _require_open_group(
        self,
        groupList: List[dict],
        lastOpenedGroupNum: int,
        libFileLine: int,
        line: str,
    ) -> dict:
        if lastOpenedGroupNum < 0 or lastOpenedGroupNum >= len(groupList):
            raise ParseError(
                "Line %s: statement outside any open group: %s"
                % (libFileLine, line.strip()[:120])
            )
        return groupList[lastOpenedGroupNum]

    def _apply_complex_attr(self, cur: dict, key: str, valueList: str) -> None:
        if key in cur:
            if isinstance(cur[key], list):
                cur[key].append(valueList)
            else:
                cur[key] = [cur[key], valueList]
        else:
            cur[key] = valueList

    def _close_groups(
        self,
        openedGroupNumList: List[int],
        n: int,
        libFileLine: int,
    ) -> int:
        for _ in range(n):
            if not openedGroupNumList:
                raise ParseError(
                    "Line %s: extra closing '}' with no open group" % libFileLine
                )
            openedGroupNumList.pop()
        return self.getLastOpenedGroupNum(openedGroupNumList)

    def _parse_file(self, lib_file: str) -> List[dict]:
        # Group: optional space before '(', optional trailing whitespace/comments after '{'
        groupCompile = re.compile(r"^(\s*)(\S+)\s*\((.*?)\)\s*\{\s*$")
        simpleAttributeCompile = re.compile(r"^(\s*)(\S+)\s*:\s*(.+?)\s*;\s*$")
        specialSimpleAttributeCompile = re.compile(r"^(\s*)(\S+)\s*:\s*(.+)\s*$")
        complexAttributeCompile = re.compile(r"^(\s*)(\S+)\s*(\(.+\))\s*;\s*$")
        specialComplexAttributeCompile = re.compile(r"^(\s*)(\S+)\s*(\(.+\))\s*$")
        multiLinesCompile = re.compile(r"^(.*)\\\s*$")
        # Allow trailing closers after the terminating ';' (pharosc: `"); }}`)
        multiLinesDoneCompile = re.compile(r"^(.*;)(\s*}*)\s*$")
        commentStartCompile = re.compile(r"^(\s*)/\*.*$")
        commentEndCompile = re.compile(r"^.*\*/\s*$")
        emptyLineCompile = re.compile(r"^\s*$")
        # Bare group-close line (after comment strip / before brace split handled separately)
        bareCloseCompile = re.compile(r"^\s*\}\s*$")

        multiLinesString = ""
        commentMark = False
        groupList: List[dict] = []
        groupListNum = 0
        openedGroupNumList: List[int] = []
        lastOpenedGroupNum = -1

        self.debug_print('>>> Parsing liberty file "%s" ...' % lib_file)
        start_seconds = int(time.time())
        libFileLine = 0

        with open(lib_file, "r", encoding="utf-8", errors="replace") as LF:
            for raw in LF:
                line = raw
                libFileLine += 1

                if commentMark:
                    if commentEndCompile.match(line):
                        commentMark = False
                    continue

                if multiLinesCompile.match(line):
                    multiLinesString = multiLinesString + multiLinesCompile.match(line).group(1)
                    continue

                if multiLinesString:
                    done_probe = _strip_line_comments(line)
                    m_done = multiLinesDoneCompile.match(done_probe)
                    if m_done:
                        # Keep any same-line closing braces for later brace-split
                        line = multiLinesString + m_done.group(1) + (m_done.group(2) or "")
                    else:
                        # incomplete multi-line; skip with warning via debug
                        self.debug_print(
                            "*Error*: Line %s: multi-lines is not finished rightly!" % libFileLine
                        )
                        multiLinesString = ""
                        continue

                # Full-line comments
                if commentStartCompile.match(line):
                    stripped_probe = _strip_line_comments(line)
                    if emptyLineCompile.match(stripped_probe):
                        if not commentEndCompile.match(line):
                            commentMark = True
                        if multiLinesString:
                            multiLinesString = ""
                        continue

                pieces = _flatten_liberty_line(line)
                if not pieces:
                    if multiLinesString:
                        multiLinesString = ""
                    continue

                statements: List[str] = []
                for piece in pieces:
                    statements.extend(_split_statements(piece))

                for content in statements:
                    if content == "}" or bareCloseCompile.match(content):
                        lastOpenedGroupNum = self._close_groups(
                            openedGroupNumList, 1, libFileLine
                        )
                        continue
                    if complexAttributeCompile.match(content):
                        m = complexAttributeCompile.match(content)
                        key, valueList = m.group(2), m.group(3)
                        cur = self._require_open_group(
                            groupList, lastOpenedGroupNum, libFileLine, content
                        )
                        self._apply_complex_attr(cur, key, valueList)
                    elif simpleAttributeCompile.match(content):
                        m = simpleAttributeCompile.match(content)
                        cur = self._require_open_group(
                            groupList, lastOpenedGroupNum, libFileLine, content
                        )
                        cur[m.group(2)] = m.group(3)
                    elif groupCompile.match(content):
                        m = groupCompile.match(content)
                        groupDepth = len(m.group(1))
                        groupType = m.group(2)
                        groupName = m.group(3)
                        lastOpenedGroupNum = self.getLastOpenedGroupNum(openedGroupNumList)
                        currentGroupDic = {
                            "fatherGroupNum": lastOpenedGroupNum,
                            "depth": groupDepth,
                            "type": groupType,
                            "name": groupName,
                        }
                        groupList.append(currentGroupDic)
                        openedGroupNumList.append(groupListNum)
                        groupListNum += 1
                        lastOpenedGroupNum = self.getLastOpenedGroupNum(openedGroupNumList)
                    elif specialComplexAttributeCompile.match(content):
                        m = specialComplexAttributeCompile.match(content)
                        key, valueList = m.group(2), m.group(3)
                        cur = self._require_open_group(
                            groupList, lastOpenedGroupNum, libFileLine, content
                        )
                        self._apply_complex_attr(cur, key, valueList)
                    elif specialSimpleAttributeCompile.match(content):
                        m = specialSimpleAttributeCompile.match(content)
                        cur = self._require_open_group(
                            groupList, lastOpenedGroupNum, libFileLine, content
                        )
                        cur[m.group(2)] = m.group(3)
                    else:
                        self.debug_print(
                            "*Error*: Line %s: Unrecognizable line: %s"
                            % (libFileLine, content.strip())
                        )


                if multiLinesString:
                    multiLinesString = ""

        end_seconds = int(time.time())
        self.debug_print("    Done")
        self.debug_print(
            "    Parse time : %s lines, %s seconds." % (libFileLine, end_seconds - start_seconds)
        )
        return groupList

    def libertyParser(self, libFile):
        """Legacy method name."""
        return self._parse_file(libFile)

    def _organize_data(self, groupList: List[dict]) -> dict:
        self.debug_print(">>> Re-organizing data structure ...")
        for i in range(len(groupList) - 1, 0, -1):
            groupDic = groupList[i]
            fatherGroupNum = groupDic["fatherGroupNum"]
            groupList[fatherGroupNum].setdefault("group", [])
            groupList[fatherGroupNum]["group"].insert(0, groupDic)
        self.debug_print("    Done")
        return groupList[0]

    def organizeData(self, groupList):
        return self._organize_data(groupList)

    # --- accessors ---
    def getUnit(self):
        unitDic = collections.OrderedDict()
        for key in self.libDic.keys():
            if re.match(r".*_unit", key):
                unitDic[key] = _strip_quotes(self.libDic[key])
        return unitDic

    def getCellList(self):
        cellList = []
        if "group" in self.libDic:
            for libGroupDic in self.libDic["group"]:
                if libGroupDic.get("type") == "cell":
                    cellList.append(libGroupDic["name"])
        return cellList

    def select_cells(self, pattern: str) -> List[str]:
        """Select cell names with shell-style wildcards (fnmatch + re.escape safe)."""
        if not pattern:
            return self.getCellList()
        # If user passes regex-ish without glob, treat as literal unless *?[] present
        cells = self.getCellList()
        return [c for c in cells if fnmatch.fnmatchcase(c, pattern)]

    def getCellArea(self, cellList=None):
        if cellList is None:
            cellList = []
        cellAreaDic = collections.OrderedDict()
        if "group" in self.libDic:
            for groupDic in self.libDic["group"]:
                if groupDic.get("type") == "cell":
                    cellName = groupDic["name"]
                    if (len(cellList) == 0) or (cellName in cellList):
                        if "area" in groupDic:
                            cellAreaDic[cellName] = groupDic["area"]
                        else:
                            cellAreaDic[cellName] = None
        for cellName in cellList:
            if cellName not in cellAreaDic:
                cellAreaDic[cellName] = None
        return cellAreaDic

    def getCellLeakagePower(self, cellList=None):
        if cellList is None:
            cellList = []
        cellLeakagePowerDic = collections.OrderedDict()
        if "group" in self.libDic:
            for groupDic in self.libDic["group"]:
                if groupDic.get("type") != "cell":
                    continue
                cellName = groupDic["name"]
                if (len(cellList) == 0) or (cellName in cellList):
                    if "group" in groupDic:
                        for cellGroupDic in groupDic["group"]:
                            if cellGroupDic.get("type") == "leakage_power":
                                leakagePowerDic = {}
                                for key, value in cellGroupDic.items():
                                    if key in ("value", "when", "related_pg_pin"):
                                        leakagePowerDic[key] = value
                                cellLeakagePowerDic.setdefault(cellName, [])
                                cellLeakagePowerDic[cellName].append(leakagePowerDic)
        return cellLeakagePowerDic

    def _getTimingGroupInfo(self, groupDic):
        timingDic = collections.OrderedDict()
        if groupDic.get("type") != "timing":
            return timingDic
        for key in ("related_pin", "related_pg_pin", "timing_sense", "timing_type", "when"):
            if key in groupDic:
                timingDic[key] = groupDic[key]
        if "group" in groupDic:
            timingDic["table_type"] = collections.OrderedDict()
            for timingLevelGroupDic in groupDic["group"]:
                ttype = timingLevelGroupDic["type"]
                tname = timingLevelGroupDic.get("name", "")
                timingDic["table_type"][ttype] = collections.OrderedDict()
                if tname:
                    timingDic["table_type"][ttype]["template_name"] = tname
                if "sigma_type" in timingLevelGroupDic:
                    timingDic["table_type"][ttype]["sigma_type"] = timingLevelGroupDic["sigma_type"]
                for idx in ("index_1", "index_2", "index_3", "values"):
                    if idx in timingLevelGroupDic:
                        timingDic["table_type"][ttype][idx] = timingLevelGroupDic[idx]
        return timingDic

    def _getInternalPowerGroupInfo(self, groupDic):
        internalPowerDic = collections.OrderedDict()
        if groupDic.get("type") != "internal_power":
            return internalPowerDic
        for key in ("related_pin", "related_pg_pin", "when"):
            if key in groupDic:
                internalPowerDic[key] = groupDic[key]
        if "group" in groupDic:
            internalPowerDic["table_type"] = collections.OrderedDict()
            for g in groupDic["group"]:
                ttype = g["type"]
                internalPowerDic["table_type"][ttype] = collections.OrderedDict()
                for idx in ("index_1", "index_2", "index_3", "values"):
                    if idx in g:
                        internalPowerDic["table_type"][ttype][idx] = g[idx]
        return internalPowerDic

    def _getPinInfo(self, groupDic):
        pinDic = collections.OrderedDict()
        if groupDic.get("type") != "pin":
            return pinDic
        if "group" in groupDic:
            for pinGroupDic in groupDic["group"]:
                pinGroupType = pinGroupDic.get("type")
                if pinGroupType == "timing":
                    pinDic.setdefault("timing", []).append(self._getTimingGroupInfo(pinGroupDic))
                elif pinGroupType == "internal_power":
                    pinDic.setdefault("internal_power", []).append(
                        self._getInternalPowerGroupInfo(pinGroupDic)
                    )
        return pinDic

    def _getBundleInfo(self, groupDic, pinList=None):
        if pinList is None:
            pinList = []
        bundleDic = collections.OrderedDict()
        local_pin_list = list(pinList)
        if "members" in groupDic:
            pinListString = groupDic["members"]
            pinListString = re.sub(r"[()\"]", "", pinListString)
            local_pin_list = [p.strip() for p in pinListString.split(",") if p.strip()]
            for pinName in local_pin_list:
                bundleDic.setdefault("pin", collections.OrderedDict())
                bundleDic["pin"].setdefault(pinName, collections.OrderedDict())
        if "group" in groupDic:
            for g in groupDic["group"]:
                groupType = g.get("type")
                if groupType == "pin":
                    pinName = g["name"]
                    if local_pin_list and pinName not in local_pin_list:
                        continue
                    bundleDic.setdefault("pin", collections.OrderedDict())
                    pinDic = self._getPinInfo(g)
                    bundleDic["pin"][pinName] = pinDic if pinDic else collections.OrderedDict()
                elif groupType == "timing":
                    bundleDic.setdefault("timing", []).append(self._getTimingGroupInfo(g))
                elif groupType == "internal_power":
                    bundleDic.setdefault("internal_power", []).append(
                        self._getInternalPowerGroupInfo(g)
                    )
        return bundleDic

    def _getBusInfo(self, groupDic, pinList=None):
        if pinList is None:
            pinList = []
        busDic = collections.OrderedDict()
        if "group" in groupDic:
            for g in groupDic["group"]:
                groupType = g.get("type")
                if groupType == "pin":
                    pinName = g["name"]
                    if pinList and pinName not in pinList:
                        continue
                    busDic.setdefault("pin", collections.OrderedDict())
                    pinDic = self._getPinInfo(g)
                    busDic["pin"][pinName] = pinDic if pinDic else collections.OrderedDict()
                elif groupType == "timing":
                    busDic.setdefault("timing", []).append(self._getTimingGroupInfo(g))
                elif groupType == "internal_power":
                    busDic.setdefault("internal_power", []).append(
                        self._getInternalPowerGroupInfo(g)
                    )
        return busDic

    def getLibPinInfo(self, cellList=None, bundleList=None, busList=None, pinList=None):
        if cellList is None:
            cellList = []
        if bundleList is None:
            bundleList = []
        if busList is None:
            busList = []
        if pinList is None:
            pinList = []

        libPinDic = collections.OrderedDict()
        if "group" not in self.libDic:
            return libPinDic

        for libGroupDic in self.libDic["group"]:
            if libGroupDic.get("type") != "cell":
                continue
            cellName = libGroupDic["name"]
            if cellList and cellName not in cellList:
                continue
            if "group" not in libGroupDic:
                continue
            for cellGroupDic in libGroupDic["group"]:
                cellGroupType = cellGroupDic.get("type")
                if cellGroupType == "pin":
                    pinName = cellGroupDic["name"]
                    if pinList and pinName not in pinList:
                        continue
                    libPinDic.setdefault("cell", collections.OrderedDict())
                    libPinDic["cell"].setdefault(cellName, collections.OrderedDict())
                    libPinDic["cell"][cellName].setdefault("pin", collections.OrderedDict())
                    pinDic = self._getPinInfo(cellGroupDic)
                    libPinDic["cell"][cellName]["pin"][pinName] = (
                        pinDic if pinDic else collections.OrderedDict()
                    )
                elif cellGroupType == "bundle":
                    bundleName = cellGroupDic["name"]
                    if bundleList and bundleName not in bundleList:
                        continue
                    bundleDic = self._getBundleInfo(cellGroupDic, pinList)
                    if bundleDic:
                        libPinDic.setdefault("cell", collections.OrderedDict())
                        libPinDic["cell"].setdefault(cellName, collections.OrderedDict())
                        libPinDic["cell"][cellName].setdefault("bundle", collections.OrderedDict())
                        libPinDic["cell"][cellName]["bundle"][bundleName] = bundleDic
                elif cellGroupType == "bus":
                    busName = cellGroupDic["name"]
                    # FIX: was incorrectly referencing bundleName (NameError)
                    if busList and busName not in busList:
                        continue
                    busDic = self._getBusInfo(cellGroupDic, pinList)
                    if busDic:
                        libPinDic.setdefault("cell", collections.OrderedDict())
                        libPinDic["cell"].setdefault(cellName, collections.OrderedDict())
                        libPinDic["cell"][cellName].setdefault("bus", collections.OrderedDict())
                        libPinDic["cell"][cellName]["bus"][busName] = busDic
        return libPinDic


# Legacy class alias
libertyParser = LibertyParser
