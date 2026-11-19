"""Tests for build_index.py. No network: plugin tests use a fake registry."""
import base64
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_index  # noqa: E402

REMOVE = object()
PACKAGE = "@example/provider"
PACKAGE_VERSION = "1.2.3"
MANIFEST_URL = "https://registry.npmjs.org/@example%2fprovider/1.2.3"
TARBALL_PATH = "@example/provider/-/provider-1.2.3.tgz"
TARBALL_URL = "https://registry.npmjs.org/" + TARBALL_PATH


def no_network(url, max_bytes):
    raise AssertionError(f"unexpected network access: {url}")


def sri(data):
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


def fake_registry(tarball=b"plugin tarball bytes", **manifest_changes):
    manifest = {
        "name": PACKAGE, "version": PACKAGE_VERSION,
        "dist": {"tarball": TARBALL_URL, "integrity": sri(tarball)},
        "peerDependencies": {"@deepseek-ai/cordis": "^4.0.0"},
    }
    for key, value in manifest_changes.items():
        if value is REMOVE:
            manifest.pop(key, None)
        else:
            manifest[key] = value
    calls = []

    def fetch(url, max_bytes):
        calls.append(url)
        if url == MANIFEST_URL:
            return json.dumps(manifest).encode("utf-8")
        if url == TARBALL_URL:
            return tarball
        raise AssertionError(f"unexpected URL {url}")

    return fetch, calls


class Tree:
    """A throwaway repository tree."""

    def __init__(self, root):
        self.root = Path(root)

    def write(self, rel, content):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return path

    def skill(self, skill_id, category="tool", skill_name=None, **changes):
        item = {"id": skill_id, "name": "测试技能", "version": "1.0.0", "description": "测试用的技能。",
                "author": "Test", "category": category}
        for key, value in changes.items():
            if value is REMOVE:
                item.pop(key, None)
            else:
                item[key] = value
        base = f"skills/{skill_id}"
        self.write(f"{base}/item.json", json.dumps(item, ensure_ascii=False, indent=2) + "\n")
        self.write(f"{base}/SKILL.md", f"---\nname: {skill_name or skill_id}\ndescription: 测试时使用。\n---\n\n# 测试\n")
        self.write(f"{base}/README.md", "# 测试\n")
        self.write(f"{base}/tool.py", "print('ok')\n")
        return self.root / base

    def plugin(self, plugin_id="example-provider", **changes):
        item = {"id": plugin_id, "name": "示例模型", "version": "1.0.0", "description": "示例模型提供方。",
                "author": "Test", "category": "model", "notices": ["可能违反第三方服务条款。"],
                "npm": {"name": PACKAGE, "version": PACKAGE_VERSION},
                "peers": ["@deepseek-ai/cordis"],
                "dsh": [{"id": "example-provider", "package": PACKAGE, "config": {"model": "x"}}]}
        for key, value in changes.items():
            if value is REMOVE:
                item.pop(key, None)
            else:
                item[key] = value
        base = f"plugins/{plugin_id}"
        self.write(f"{base}/item.json", json.dumps(item, ensure_ascii=False, indent=2) + "\n")
        self.write(f"{base}/README.md", "# 示例\n")
        return self.root / base


class BuildTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tree = Tree(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, fetch=no_network, **kwargs):
        return build_index.build(self.tree.root, fetch=fetch, **kwargs)

    def index(self, **kwargs):
        return json.loads(self.build(**kwargs))

    def assertBuildFails(self, *fragments, fetch=no_network, **kwargs):
        with self.assertRaises(build_index.BuildError) as caught:
            self.build(fetch=fetch, **kwargs)
        text = "\n".join(caught.exception.errors)
        for fragment in fragments:
            self.assertIn(fragment, text)
        return caught.exception.errors


class SkillIndexTest(BuildTestCase):
    def test_skill_entry_shape(self):
        folder = self.tree.skill("sample", notices=["会联网。"], minHostVersion="1.12.0")
        self.tree.write("skills/sample/lib/helper.py", "X = 1\n")
        entry = self.index()["items"][0]
        self.assertEqual(list(entry), ["id", "kind", "name", "version", "description", "author", "category",
                                       "minHostVersion", "notices", "readme", "files"])
        self.assertEqual(entry["kind"], "skill")
        self.assertEqual(entry["notices"], ["会联网。"])
        readme = (folder / "README.md").read_bytes()
        self.assertEqual(entry["readme"], {"url": "skills/sample/README.md",
                                           "sha256": hashlib.sha256(readme).hexdigest(), "bytes": len(readme)})
        self.assertEqual([f["path"] for f in entry["files"]], ["SKILL.md", "lib/helper.py", "tool.py"])
        for record in entry["files"]:
            self.assertEqual(list(record), ["path", "url", "sha256", "bytes"])
            data = (self.tree.root / record["url"]).read_bytes()
            self.assertEqual(record["url"], "skills/sample/" + record["path"])
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(record["bytes"], len(data))

    def test_optional_fields_left_out_or_defaulted(self):
        self.tree.skill("sample")
        entry = self.index()["items"][0]
        self.assertNotIn("minHostVersion", entry)
        self.assertEqual(entry["notices"], [])

    def test_output_is_deterministic_and_sorted(self):
        self.tree.skill("zeta", category="danmaku")
        self.tree.skill("beta", category="bt")
        self.tree.skill("alpha", category="tool")
        self.tree.skill("aardvark", category="bt")
        first = self.build()
        self.assertEqual(first, self.build())
        self.assertTrue(first.endswith("}\n"))
        self.assertIn('\n  "items": [\n    {\n      "id": "aardvark"', first)
        self.assertIn("测试技能", first)  # UTF-8, not \u escapes
        ids = [item["id"] for item in json.loads(first)["items"]]
        self.assertEqual(ids, ["aardvark", "beta", "zeta", "alpha"])
        self.assertEqual(list(json.loads(first)), ["version", "items"])
        self.assertEqual(json.loads(first)["version"], 1)

    def test_empty_repository(self):
        self.assertEqual(self.build(), '{\n  "version": 1,\n  "items": []\n}\n')

    def test_skills_need_no_network(self):
        self.tree.skill("sample")
        self.build(fetch=no_network)  # no plugins: the fetcher must never be called


class ItemValidationTest(BuildTestCase):
    CASES = [
        ({"icon": "x.png"}, "unknown key 'icon'"),
        ({"description": REMOVE}, "missing key 'description'"),
        ({"author": REMOVE}, "missing key 'author'"),
        ({"version": "1.0"}, "'version' must be a semantic version"),
        ({"version": "v1.0.0"}, "'version' must be a semantic version"),
        ({"version": "01.0.0"}, "'version' must be a semantic version"),
        ({"description": "长" * 121}, "'description' is 121 characters; the limit is 120"),
        ({"description": "两行\n说明"}, "'description' must be one line"),
        ({"description": "  "}, "'description' must be a non-empty string"),
        ({"name": 3}, "'name' must be a non-empty string"),
        ({"category": "video"}, "'category' must be one of bt, danmaku, model, tool"),
        ({"notices": "注意"}, "'notices' must be a list"),
        ({"notices": ["好", 1]}, "'notices' must be a list"),
        ({"notices": [""]}, "'notices' must be a list"),
        ({"notices": ["x"] * 9}, "'notices' must be a list"),
        ({"minHostVersion": "latest"}, "'minHostVersion' must be a semantic version"),
        ({"id": "other"}, "'id' is 'other' but the folder is 'sample'"),
        ({"npm": {"name": "x", "version": "1.0.0"}}, "unknown key 'npm'"),
    ]

    def test_item_fields(self):
        for changes, message in self.CASES:
            with self.subTest(changes=changes):
                self.tree = Tree(tempfile.mkdtemp(dir=self._tmp.name))
                self.tree.skill("sample", **changes)
                self.assertBuildFails("skills/sample: " + message)

    def test_item_json_must_be_json_object(self):
        folder = self.tree.skill("sample")
        (folder / "item.json").write_text("[1, 2]", encoding="utf-8")
        self.assertBuildFails("item.json must be a JSON object")
        (folder / "item.json").write_text("{nope", encoding="utf-8")
        self.assertBuildFails("item.json is not valid UTF-8 JSON")
        (folder / "item.json").unlink()
        self.assertBuildFails("skills/sample: missing item.json")

    def test_every_problem_is_reported(self):
        self.tree.skill("one", version="1")
        self.tree.skill("two", category="nope")
        errors = self.assertBuildFails("skills/one:", "skills/two:")
        self.assertEqual(len(errors), 2)


class FileRuleTest(BuildTestCase):
    def test_hidden_file(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/.DS_Store", b"\0")
        self.assertBuildFails(".DS_Store is hidden")

    def test_hidden_folder(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/.cache/x.py", "")
        self.assertBuildFails(".cache/ is hidden")

    def test_pycache(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/__pycache__/tool.cpython-311.pyc", b"\0")
        self.assertBuildFails("__pycache__/ is a __pycache__ folder")

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_symlinks(self):
        folder = self.tree.skill("sample")
        try:
            os.symlink(folder / "tool.py", folder / "link.py")
            os.symlink(folder.parent, folder / "up")
        except OSError:
            self.skipTest("cannot create symlinks here")
        self.assertBuildFails("link.py is a symlink", "up/ is a symlink")

    def test_unsafe_names(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/my tool.py", "")
        self.tree.write("skills/sample/中文.py", "")
        self.tree.write("skills/sample/a..b.py", "")
        self.assertBuildFails("my tool.py has characters outside", "中文.py has characters outside",
                              "a..b.py has characters outside")

    def test_too_many_files(self):
        self.tree.skill("sample")
        for i in range(build_index.MAX_FILES):  # SKILL.md + tool.py + 64 = 66 listed
            self.tree.write(f"skills/sample/data/f{i:02d}.txt", "x")
        self.assertBuildFails("has 66 files; the limit is 64")

    def test_file_limit_counts_listed_files_only(self):
        self.tree.skill("sample")
        for i in range(build_index.MAX_FILES - 2):  # 64 listed; item.json and README.md are extra
            self.tree.write(f"skills/sample/data/f{i:02d}.txt", "x")
        self.assertEqual(len(self.index()["items"][0]["files"]), build_index.MAX_FILES)

    def test_file_too_large(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/big.bin", b"\0" * (build_index.MAX_FILE_BYTES + 1))
        self.assertBuildFails(f"big.bin is {build_index.MAX_FILE_BYTES + 1} bytes")

    def test_text_must_be_utf8(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/tool.py", "print('你好')\n".encode("gbk"))
        self.assertBuildFails("tool.py is not UTF-8 text")

    def test_required_files(self):
        folder = self.tree.skill("sample")
        (folder / "SKILL.md").unlink()
        (folder / "README.md").unlink()
        self.assertBuildFails("missing SKILL.md", "missing README.md")

    def test_skill_md_frontmatter(self):
        folder = self.tree.skill("sample", skill_name="another")
        self.assertBuildFails("frontmatter 'name' must be 'sample'")
        (folder / "SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
        self.assertBuildFails("must start with YAML frontmatter")
        (folder / "SKILL.md").write_text("---\nname: sample\ndescription: >\n  多行\n---\n", encoding="utf-8")
        self.assertBuildFails("needs a one-line 'description'")
        (folder / "SKILL.md").write_text("---\nname: sample\ndescription: x\n", encoding="utf-8")
        self.assertBuildFails("frontmatter is not closed")

    def test_case_insensitive_duplicates(self):
        self.tree.skill("sample")
        self.tree.write("skills/sample/Data.txt", "a")
        self.tree.write("skills/sample/data.txt", "b")
        if len(list((self.tree.root / "skills/sample").glob("*.txt"))) < 2:
            self.skipTest("case-insensitive file system")
        self.assertBuildFails("differ only in letter case")

    def test_folder_names_and_stray_files(self):
        self.tree.skill("sample")
        self.tree.write("skills/Bad_Id/item.json", "{}")
        self.tree.write("skills/notes.txt", "x")
        self.tree.write("skills/.DS_Store", b"\0")
        self.assertBuildFails("skills/Bad_Id: folder name must be an id", "skills/notes.txt: only item folders",
                              "skills/.DS_Store: is hidden")


class PluginTest(BuildTestCase):
    def test_plugin_entry(self):
        self.tree.plugin()
        fetch, calls = fake_registry()
        entry = self.index(fetch=fetch)["items"][0]
        self.assertEqual(calls, [MANIFEST_URL, TARBALL_URL])
        self.assertEqual(list(entry), ["id", "kind", "name", "version", "description", "author", "category",
                                       "notices", "readme", "packages", "peers", "dsh"])
        self.assertEqual(entry["kind"], "plugin")
        tarball = b"plugin tarball bytes"
        self.assertEqual(entry["packages"], [{
            "path": "node_modules/@example/provider", "name": PACKAGE, "version": PACKAGE_VERSION,
            "url": TARBALL_PATH, "sha256": hashlib.sha256(tarball).hexdigest(), "bytes": len(tarball)}])
        self.assertEqual(entry["peers"], ["@deepseek-ai/cordis"])
        self.assertEqual(entry["dsh"], [{"id": "example-provider", "package": PACKAGE, "config": {"model": "x"}}])

    def test_unscoped_package(self):
        self.tree.plugin(npm={"name": "plain-provider", "version": "2.0.0"},
                         dsh=[{"id": "plain", "package": "plain-provider"}])
        tarball = b"x"
        manifest = {"name": "plain-provider", "version": "2.0.0",
                    "dist": {"tarball": "https://registry.npmjs.org/plain-provider/-/plain-provider-2.0.0.tgz",
                             "integrity": sri(tarball)}}

        def fetch(url, max_bytes):
            if url == "https://registry.npmjs.org/plain-provider/2.0.0":
                return json.dumps(manifest).encode()
            self.assertEqual(url, "https://registry.npmjs.org/plain-provider/-/plain-provider-2.0.0.tgz")
            return tarball

        package = self.index(fetch=fetch)["items"][0]["packages"][0]
        self.assertEqual(package["url"], "plain-provider/-/plain-provider-2.0.0.tgz")
        self.assertEqual(package["path"], "node_modules/plain-provider")

    def test_runtime_dependencies_must_be_peers_or_bundled(self):
        self.tree.plugin()
        fetch, calls = fake_registry(dependencies={"left-pad": "1.3.0", "@deepseek-ai/cordis": "^4"})
        self.assertBuildFails("depends on left-pad", fetch=fetch)
        self.assertEqual(calls, [MANIFEST_URL])  # refused before downloading the tarball
        fetch, _ = fake_registry(dependencies={"left-pad": "1.3.0"}, bundleDependencies=["left-pad"])
        self.build(fetch=fetch)

    def test_required_peer_dependencies_must_be_listed(self):
        self.tree.plugin(peers=[])
        fetch, _ = fake_registry()
        self.assertBuildFails("peer dependency @deepseek-ai/cordis", fetch=fetch)
        fetch, _ = fake_registry(peerDependenciesMeta={"@deepseek-ai/cordis": {"optional": True}})
        self.build(fetch=fetch)

    def test_install_scripts_are_refused(self):
        self.tree.plugin()
        for changes in ({"scripts": {"postinstall": "node setup.js", "test": "x"}},
                        {"scripts": {"install": "node-gyp rebuild"}},
                        {"gypfile": True}):
            with self.subTest(changes=changes):
                fetch, _ = fake_registry(**changes)
                self.assertBuildFails("install", fetch=fetch)

    def test_integrity_and_tarball_location(self):
        self.tree.plugin()
        fetch, _ = fake_registry(dist={"tarball": TARBALL_URL, "integrity": sri(b"something else")})
        self.assertBuildFails("does not match the registry's integrity", fetch=fetch)
        fetch, _ = fake_registry(dist={"tarball": TARBALL_URL, "integrity": "sha1-abc"})
        self.assertBuildFails("no sha512 integrity", fetch=fetch)
        fetch, _ = fake_registry(dist={"tarball": "https://evil.example/provider-1.2.3.tgz",
                                       "integrity": sri(b"plugin tarball bytes")})
        self.assertBuildFails("dist.tarball is", fetch=fetch)

    def test_registry_must_have_the_version(self):
        self.tree.plugin()
        fetch, _ = fake_registry(version="9.9.9")
        self.assertBuildFails("the registry has no such version", fetch=fetch)

    def test_plugin_fields(self):
        cases = [
            ({"npm": {"name": PACKAGE, "version": "^1.2.3"}}, "one exact version"),
            ({"npm": {"name": "Bad Name", "version": "1.0.0"}}, "not a valid npm package name"),
            ({"npm": {"name": PACKAGE}}, "'npm' must be"),
            ({"npm": REMOVE}, "missing key 'npm'"),
            ({"dsh": []}, "'dsh' must be a list of 1 to 8 rows"),
            ({"dsh": [{"id": "x", "package": "other"}]}, "'package' must be the plugin's npm package name"),
            ({"dsh": [{"id": "nipa-x", "package": PACKAGE}]}, "must not start with nipa-"),
            ({"dsh": [{"id": "Bad", "package": PACKAGE}]}, "'id' must match"),
            ({"dsh": [{"id": "x", "package": PACKAGE, "config": []}]}, "'config' must be an object"),
            ({"dsh": [{"id": "x", "package": PACKAGE, "inject": "a"}]}, "'inject' must be a list of strings"),
            ({"dsh": [{"id": "x", "package": PACKAGE, "extra": 1}]}, "unknown key 'extra'"),
            ({"peers": ["Not Valid"]}, "'peers' must be a list of npm package names"),
            ({"peers": [PACKAGE]}, "must not contain the plugin's own package"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                self.tree = Tree(tempfile.mkdtemp(dir=self._tmp.name))
                self.tree.plugin(**changes)
                self.assertBuildFails(message)  # rejected before any network access

    def test_plugin_folder_holds_only_item_and_readme(self):
        self.tree.plugin()
        self.tree.write("plugins/example-provider/index.js", "")
        self.assertBuildFails("index.js: a plugin folder holds only item.json and README.md")

    def test_same_id_for_skill_and_plugin(self):
        self.tree.skill("example-provider")
        self.tree.plugin()
        fetch, _ = fake_registry()
        self.assertBuildFails("the same id is used by a skill and a plugin", fetch=fetch)

    def test_offline_reuses_recorded_packages(self):
        self.tree.plugin()
        self.tree.skill("sample")
        fetch, _ = fake_registry()
        text = self.build(fetch=fetch)
        self.tree.write("index.json", text)
        self.assertEqual(self.build(fetch=no_network, offline=True), text)
        self.tree.plugin(npm={"name": PACKAGE, "version": "1.2.4"})
        self.assertBuildFails("--offline: index.json has no record", offline=True)


class MainTest(BuildTestCase):
    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = build_index.main([*args, "--root", str(self.tree.root)])
        return code, out.getvalue(), err.getvalue()

    def test_write_then_check(self):
        folder = self.tree.skill("sample")
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("index.json is stale", err)
        code, out, _ = self.run_main()
        self.assertEqual((code, out.strip()), (0, "wrote index.json (1 items)"))
        written = (self.tree.root / "index.json").read_bytes()
        self.assertNotIn(b"\r\n", written)
        self.assertEqual(self.run_main("--check")[0], 0)
        (folder / "tool.py").write_text("print('changed')\n", encoding="utf-8")
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("index.json (committed)", err)
        self.assertEqual((self.tree.root / "index.json").read_bytes(), written)  # --check never writes

    def test_invalid_items_fail_both_modes(self):
        self.tree.skill("sample", category="nope")
        for args in ((), ("--check",)):
            code, _, err = self.run_main(*args)
            self.assertEqual(code, 1)
            self.assertIn("'category' must be one of", err)
        self.assertFalse((self.tree.root / "index.json").exists())


if __name__ == "__main__":
    unittest.main()
