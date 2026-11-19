#!/usr/bin/env python3
"""Build index.json, the list NipaPlay reads, from skills/<id>/ and plugins/<id>/.

  python3 tools/build_index.py            validate every item and write index.json
  python3 tools/build_index.py --check    exit 1 if an item is invalid or index.json is stale
  python3 tools/build_index.py --offline  reuse plugin package records already in index.json

Skills need no network. A plugin's npm tarball is fetched from the registry,
checked against npm's sha512 integrity and pinned by SHA-256.
"""
import argparse
import base64
import difflib
import hashlib
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = "index.json"
INDEX_VERSION = 1
REGISTRY = "https://registry.npmjs.org"
USER_AGENT = "rika-plugins-build/1 (+https://github.com/AimesSoft/rika_plugins)"

ID = re.compile(r"[a-z0-9][a-z0-9-]{0,47}")
SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
NPM_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")
DSH_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
PATH = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")
CATEGORIES = ("bt", "danmaku", "model", "tool")

MAX_FILES = 64
MAX_FILE_BYTES = 1 << 20
MAX_PACKAGE_BYTES = 32 << 20
MAX_URL = 200
MAX_NAME = 80
MAX_DESCRIPTION = 120
MAX_AUTHOR = 120
MAX_NOTICES = 8
MAX_NOTICE = 600
MAX_SKILL_DESCRIPTION = 1024
MAX_DSH_ROWS = 8

COMMON_REQUIRED = ("id", "name", "version", "description", "author", "category")
COMMON_OPTIONAL = ("minHostVersion", "notices")
PLUGIN_REQUIRED = ("npm", "dsh")
PLUGIN_OPTIONAL = ("peers",)
INSTALL_HOOKS = ("preinstall", "install", "postinstall")
TEXT_SUFFIXES = (".md", ".py", ".json", ".txt")


class BuildError(Exception):
    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = list(errors)


class Problems:
    """Collects every problem so one run reports them all."""

    def __init__(self):
        self.errors = []

    def add(self, where, message):
        self.errors.append(f"{where}: {message}")

    def raise_if_any(self):
        if self.errors:
            raise BuildError(self.errors)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- item.json

def _text(item, key, where, problems, limit):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.add(where, f"'{key}' must be a non-empty string")
        return False
    if value != value.strip() or "\n" in value or "\r" in value:
        problems.add(where, f"'{key}' must be one line without surrounding spaces")
        return False
    if len(value) > limit:
        problems.add(where, f"'{key}' is {len(value)} characters; the limit is {limit}")
        return False
    return True


def validate_item(item, folder_id, kind, where, problems):
    """Checks item.json strictly; returns True when it can be indexed."""
    before = len(problems.errors)
    if not isinstance(item, dict):
        problems.add(where, "item.json must be a JSON object")
        return False
    required = COMMON_REQUIRED + (PLUGIN_REQUIRED if kind == "plugin" else ())
    allowed = set(required + COMMON_OPTIONAL + (PLUGIN_OPTIONAL if kind == "plugin" else ()))
    for key in item:
        if key not in allowed:
            problems.add(where, f"unknown key '{key}'")
    for key in required:
        if key not in item:
            problems.add(where, f"missing key '{key}'")

    item_id = item.get("id")
    if "id" in item:
        if not isinstance(item_id, str) or not ID.fullmatch(item_id):
            problems.add(where, "'id' must match ^[a-z0-9][a-z0-9-]{0,47}$")
        elif item_id != folder_id:
            problems.add(where, f"'id' is '{item_id}' but the folder is '{folder_id}'")
    if "name" in item:
        _text(item, "name", where, problems, MAX_NAME)
    if "version" in item:
        version = item["version"]
        if not isinstance(version, str) or len(version) > 64 or not SEMVER.fullmatch(version):
            problems.add(where, "'version' must be a semantic version such as 1.0.0")
    if "description" in item:
        _text(item, "description", where, problems, MAX_DESCRIPTION)
    if "author" in item:
        _text(item, "author", where, problems, MAX_AUTHOR)
    if "category" in item and item["category"] not in CATEGORIES:
        problems.add(where, "'category' must be one of " + ", ".join(CATEGORIES))
    if "minHostVersion" in item:
        host = item["minHostVersion"]
        if not isinstance(host, str) or len(host) > 64 or not SEMVER.fullmatch(host):
            problems.add(where, "'minHostVersion' must be a semantic version such as 1.12.0")
    if "notices" in item:
        notices = item["notices"]
        if not isinstance(notices, list) or len(notices) > MAX_NOTICES or any(
                not isinstance(n, str) or not n.strip() or len(n) > MAX_NOTICE for n in notices):
            problems.add(where, f"'notices' must be a list of at most {MAX_NOTICES} non-empty "
                                f"strings of at most {MAX_NOTICE} characters")
    if kind == "plugin":
        _validate_plugin_fields(item, where, problems)
    return len(problems.errors) == before


def _validate_plugin_fields(item, where, problems):
    npm = item.get("npm")
    package = None
    if "npm" in item:
        if not isinstance(npm, dict) or set(npm) != {"name", "version"}:
            problems.add(where, "'npm' must be {\"name\": ..., \"version\": ...} and nothing else")
        else:
            name, version = npm["name"], npm["version"]
            if not isinstance(name, str) or len(name) > 214 or not NPM_NAME.fullmatch(name):
                problems.add(where, "'npm.name' is not a valid npm package name")
            else:
                package = name
            if not isinstance(version, str) or not SEMVER.fullmatch(version):
                problems.add(where, "'npm.version' must be one exact version (no range or dist-tag)")
    if "peers" in item:
        peers = item["peers"]
        if not isinstance(peers, list) or any(
                not isinstance(p, str) or len(p) > 214 or not NPM_NAME.fullmatch(p) for p in peers):
            problems.add(where, "'peers' must be a list of npm package names")
        elif len(set(peers)) != len(peers):
            problems.add(where, "'peers' lists a package twice")
        elif package in peers:
            problems.add(where, "'peers' must not contain the plugin's own package")
    if "dsh" in item:
        rows = item["dsh"]
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_DSH_ROWS:
            problems.add(where, f"'dsh' must be a list of 1 to {MAX_DSH_ROWS} rows")
            return
        seen = set()
        for i, row in enumerate(rows, 1):
            at = f"{where} dsh[{i}]"
            if not isinstance(row, dict):
                problems.add(at, "must be an object")
                continue
            for key in row:
                if key not in ("id", "package", "config", "inject"):
                    problems.add(at, f"unknown key '{key}'")
            row_id = row.get("id")
            if not isinstance(row_id, str) or not DSH_ID.fullmatch(row_id):
                problems.add(at, "'id' must match ^[a-z0-9][a-z0-9._-]{0,63}$")
            elif row_id.startswith("nipa-"):
                problems.add(at, "'id' must not start with nipa- (reserved for NipaPlay)")
            elif row_id in seen:
                problems.add(at, f"'id' {row_id} is used twice")
            seen.add(row_id)
            if row.get("package") != package:
                problems.add(at, "'package' must be the plugin's npm package name")
            if "config" in row and not isinstance(row["config"], dict):
                problems.add(at, "'config' must be an object")
            if "inject" in row and (not isinstance(row["inject"], list) or any(
                    not isinstance(v, str) for v in row["inject"])):
                problems.add(at, "'inject' must be a list of strings")


# ---------------------------------------------------------------- files

def scan_folder(folder, where, problems):
    """Every regular file under folder as sorted POSIX relative paths."""
    found = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        rel_dir = Path(dirpath).relative_to(folder).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        for name in sorted(dirnames):
            full = os.path.join(dirpath, name)
            rel = prefix + name
            reason = None
            if os.path.islink(full):
                reason = "is a symlink"
            elif name == "__pycache__":
                reason = "is a __pycache__ folder; delete it (run scripts with PYTHONDONTWRITEBYTECODE=1)"
            elif name.startswith("."):
                reason = "is hidden"
            if reason:
                problems.add(where, f"{rel}/ {reason}")
                dirnames.remove(name)
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = prefix + name
            mode = os.lstat(full).st_mode
            if stat.S_ISLNK(mode):
                problems.add(where, f"{rel} is a symlink")
            elif name.startswith("."):
                problems.add(where, f"{rel} is hidden; delete it")
            elif not stat.S_ISREG(mode):
                problems.add(where, f"{rel} is not a regular file")
            elif ".." in rel or not PATH.fullmatch(rel):
                problems.add(where, f"{rel} has characters outside [A-Za-z0-9._/-]")
            else:
                found.append(rel)
    found.sort()
    lowered = {}
    for rel in found:
        if rel.lower() in lowered:
            problems.add(where, f"{rel} and {lowered[rel.lower()]} differ only in letter case")
        lowered[rel.lower()] = rel
    return found


def file_record(root, url, problems, where, path=None):
    data = (root / url).read_bytes()
    if len(data) > MAX_FILE_BYTES:
        problems.add(where, f"{url} is {len(data)} bytes; the limit is {MAX_FILE_BYTES}")
    if len(url) > MAX_URL:
        problems.add(where, f"{url} is longer than {MAX_URL} characters")
    if url.endswith(TEXT_SUFFIXES):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            problems.add(where, f"{url} is not UTF-8 text")
    record = {} if path is None else {"path": path}
    record.update({"url": url, "sha256": sha256_hex(data), "bytes": len(data)})
    return record


def skill_frontmatter(text, folder_id, where, problems):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        problems.add(where, "SKILL.md must start with YAML frontmatter (---)")
        return
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match:
            value = match[2].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            fields[match[1]] = value
    else:
        problems.add(where, "SKILL.md frontmatter is not closed with ---")
        return
    if fields.get("name") != folder_id:
        problems.add(where, f"SKILL.md frontmatter 'name' must be '{folder_id}'")
    description = fields.get("description", "")
    if not description or description in {">", "|", ">-", "|-"}:
        problems.add(where, "SKILL.md frontmatter needs a one-line 'description'")
    elif len(description) > MAX_SKILL_DESCRIPTION:
        problems.add(where, f"SKILL.md 'description' is longer than {MAX_SKILL_DESCRIPTION} characters")


def load_json(path, where, problems):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problems.add(where, f"missing {path.name}")
    except (UnicodeDecodeError, ValueError) as exc:
        problems.add(where, f"{path.name} is not valid UTF-8 JSON ({exc})")
    return None


def common_entry(item, kind):
    entry = {"id": item["id"], "kind": kind}
    for key in ("name", "version", "description", "author", "category"):
        entry[key] = item[key]
    if "minHostVersion" in item:
        entry["minHostVersion"] = item["minHostVersion"]
    entry["notices"] = list(item.get("notices", []))
    return entry


def skill_entry(root, folder_id, problems):
    where = f"skills/{folder_id}"
    folder = root / "skills" / folder_id
    before = len(problems.errors)
    item = load_json(folder / "item.json", where, problems)
    if item is not None:
        validate_item(item, folder_id, "skill", where, problems)
    paths = scan_folder(folder, where, problems)
    for required in ("SKILL.md", "README.md"):
        if required not in paths:
            problems.add(where, f"missing {required}")
    listed = [p for p in paths if p not in ("item.json", "README.md")]
    if len(listed) > MAX_FILES:
        problems.add(where, f"has {len(listed)} files; the limit is {MAX_FILES}")
    if "SKILL.md" in paths:
        try:
            skill_frontmatter((folder / "SKILL.md").read_text(encoding="utf-8"), folder_id, where, problems)
        except UnicodeDecodeError:
            pass  # reported by file_record
    readme = file_record(root, f"{where}/README.md", problems, where) if "README.md" in paths else None
    if "item.json" in paths:
        file_record(root, f"{where}/item.json", problems, where)  # size and encoding only
    files = [file_record(root, f"{where}/{p}", problems, where, path=p) for p in listed]
    if len(problems.errors) != before:
        return None
    entry = common_entry(item, "skill")
    entry["readme"] = readme
    entry["files"] = files
    return entry


# ---------------------------------------------------------------- plugins

def http_fetch(url, max_bytes):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise BuildError([f"{url}: HTTP {exc.code}"]) from None
    except (urllib.error.URLError, OSError) as exc:
        raise BuildError([f"{url}: {getattr(exc, 'reason', exc)}"]) from None
    if len(body) > max_bytes:
        raise BuildError([f"{url}: larger than {max_bytes} bytes"])
    return body


def tarball_path(name, version):
    return f"{name}/-/{name.split('/')[-1]}-{version}.tgz"


def matches_integrity(data, integrity):
    digest = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    return any(value == digest for value in integrity.split())


def resolve_package(name, version, peers, fetch):
    """The pinned record of name@version, or BuildError explaining why not."""
    where = f"npm {name}@{version}"
    doc_url = f"{REGISTRY}/{name.replace('/', '%2f')}/{urllib.parse.quote(version)}"
    try:
        doc = json.loads(fetch(doc_url, 4 << 20).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise BuildError([f"{where}: the registry did not return a package manifest"]) from None
    if not isinstance(doc, dict) or doc.get("name") != name or doc.get("version") != version:
        raise BuildError([f"{where}: the registry has no such version"])
    reasons = []
    scripts = doc.get("scripts") if isinstance(doc.get("scripts"), dict) else {}
    hooks = [hook for hook in INSTALL_HOOKS if hook in scripts]
    if hooks:
        reasons.append("has install scripts (" + ", ".join(f"{h}: {scripts[h]}" for h in hooks)
                       + "); NipaPlay does not run install scripts")
    elif doc.get("gypfile") is True or doc.get("hasInstallScript") is True:
        reasons.append("needs a native build at install time; NipaPlay does not run install scripts")
    bundled = doc.get("bundleDependencies", doc.get("bundledDependencies")) or []
    dependencies = doc.get("dependencies") if isinstance(doc.get("dependencies"), dict) else {}
    if bundled is True:
        bundled = list(dependencies)
    bundled = set(b for b in bundled if isinstance(b, str)) if isinstance(bundled, list) else set()
    for dependency in sorted(dependencies):
        if dependency not in peers and dependency not in bundled:
            reasons.append(f"depends on {dependency}, which is neither in 'peers' (provided by the DSH "
                           f"runtime) nor bundled; v1 plugins take runtime dependencies from DSH only")
    peer_deps = doc.get("peerDependencies") if isinstance(doc.get("peerDependencies"), dict) else {}
    meta = doc.get("peerDependenciesMeta") if isinstance(doc.get("peerDependenciesMeta"), dict) else {}
    for peer in sorted(peer_deps):
        optional = isinstance(meta.get(peer), dict) and meta[peer].get("optional") is True
        if peer not in peers and not optional:
            reasons.append(f"has peer dependency {peer}, which is not in 'peers'")
    dist = doc.get("dist") if isinstance(doc.get("dist"), dict) else {}
    integrity = dist.get("integrity")
    if not isinstance(integrity, str) or "sha512-" not in integrity:
        reasons.append("the registry gives no sha512 integrity for its tarball")
    expected = tarball_path(name, version)
    tarball = dist.get("tarball")
    split = urllib.parse.urlsplit(tarball if isinstance(tarball, str) else "")
    if (split.scheme, split.netloc) != ("https", "registry.npmjs.org") or \
            urllib.parse.unquote(split.path.lstrip("/")) != expected:
        reasons.append(f"dist.tarball is {tarball!r}, expected {REGISTRY}/{expected}")
    if reasons:
        raise BuildError([f"{where}: {reason}" for reason in reasons])
    data = fetch(f"{REGISTRY}/{expected}", MAX_PACKAGE_BYTES)
    if not matches_integrity(data, integrity):
        raise BuildError([f"{where}: the tarball does not match the registry's integrity {integrity}"])
    return {"path": f"node_modules/{name}", "name": name, "version": version,
            "url": expected, "sha256": sha256_hex(data), "bytes": len(data)}


def plugin_entry(root, folder_id, problems, fetch, previous, offline):
    where = f"plugins/{folder_id}"
    folder = root / "plugins" / folder_id
    before = len(problems.errors)
    item = load_json(folder / "item.json", where, problems)
    if item is not None:
        validate_item(item, folder_id, "plugin", where, problems)
    paths = scan_folder(folder, where, problems)
    for extra in paths:
        if extra not in ("item.json", "README.md"):
            problems.add(where, f"{extra}: a plugin folder holds only item.json and README.md; "
                                "the code comes from npm")
    if "README.md" not in paths:
        problems.add(where, "missing README.md")
    readme = file_record(root, f"{where}/README.md", problems, where) if "README.md" in paths else None
    if len(problems.errors) != before:
        return None
    entry = common_entry(item, "plugin")
    entry["readme"] = readme
    name, version = item["npm"]["name"], item["npm"]["version"]
    peers = list(item.get("peers", []))
    if offline:
        old = (previous or {}).get(folder_id) or {}
        packages = old.get("packages") or []
        if len(packages) == 1 and packages[0].get("name") == name and packages[0].get("version") == version:
            package = packages[0]
        else:
            problems.add(where, f"--offline: index.json has no record of {name}@{version}; run without --offline")
            return None
    else:
        try:
            package = resolve_package(name, version, set(peers), fetch)
        except BuildError as exc:
            for error in exc.errors:
                problems.add(where, error)
            return None
    entry["packages"] = [package]
    entry["peers"] = peers
    rows = []
    for row in item["dsh"]:
        out = {"id": row["id"], "package": row["package"]}
        if "config" in row:
            out["config"] = row["config"]
        if "inject" in row:
            out["inject"] = row["inject"]
        rows.append(out)
    entry["dsh"] = rows
    return entry


# ---------------------------------------------------------------- index

def item_folders(root, kind_dir, problems):
    base = root / kind_dir
    if not base.exists():
        return []
    folders = []
    for child in sorted(base.iterdir(), key=lambda p: p.name):
        rel = f"{kind_dir}/{child.name}"
        if child.is_symlink():
            problems.add(rel, "is a symlink")
        elif child.name.startswith("."):
            problems.add(rel, "is hidden; delete it")
        elif not child.is_dir():
            problems.add(rel, f"only item folders belong in {kind_dir}/")
        elif not ID.fullmatch(child.name):
            problems.add(rel, "folder name must be an id matching ^[a-z0-9][a-z0-9-]{0,47}$")
        else:
            folders.append(child.name)
    return folders


def previous_items(root):
    try:
        data = json.loads((root / INDEX).read_text(encoding="utf-8"))
        return {item["id"]: item for item in data.get("items", []) if isinstance(item, dict) and "id" in item}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}


def build(root, fetch=http_fetch, offline=False):
    """The text of index.json for the tree at root; raises BuildError."""
    root = Path(root)
    problems = Problems()
    previous = previous_items(root) if offline else None
    items = []
    skills = item_folders(root, "skills", problems)
    plugins = item_folders(root, "plugins", problems)
    for folder_id in sorted(set(skills) & set(plugins)):
        problems.add(folder_id, "the same id is used by a skill and a plugin")
    for folder_id in skills:
        entry = skill_entry(root, folder_id, problems)
        if entry:
            items.append(entry)
    for folder_id in plugins:
        entry = plugin_entry(root, folder_id, problems, fetch, previous, offline)
        if entry:
            items.append(entry)
    problems.raise_if_any()
    items.sort(key=lambda entry: (entry["category"], entry["id"]))
    index = {"version": INDEX_VERSION, "items": items}
    return json.dumps(index, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="do not write; exit 1 if index.json is stale or invalid")
    parser.add_argument("--offline", action="store_true",
                        help="reuse plugin package records from the existing index.json instead of the registry")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this repository)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    target = args.root / INDEX
    try:
        text = build(args.root, offline=args.offline)
    except BuildError as exc:
        print(f"{len(exc.errors)} problem(s):", file=sys.stderr)
        for error in exc.errors:
            print("  " + error, file=sys.stderr)
        return 1
    count = len(json.loads(text)["items"])
    if args.check:
        try:
            current = target.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            current = None
        if current != text:
            print(f"{INDEX} is stale; run: python3 tools/build_index.py", file=sys.stderr)
            if current is not None:
                diff = difflib.unified_diff(current.splitlines(), text.splitlines(),
                                            f"{INDEX} (committed)", f"{INDEX} (built)", lineterm="", n=1)
                for line in list(diff)[:60]:
                    print(line, file=sys.stderr)
            return 1
        print(f"{INDEX} is up to date ({count} items)")
        return 0
    with open(target, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    print(f"wrote {INDEX} ({count} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
