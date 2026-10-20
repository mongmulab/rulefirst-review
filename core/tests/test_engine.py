import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from rulefirst import changes, cli, config, llm, rules, verify  # noqa: E402


def sh(repo, *args):
    subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=repo, check=True, capture_output=True)


class RepoCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="rfr-"))
        sh(self.dir, "init", "-q")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self):
        sh(self.dir, "add", "-A")
        sh(self.dir, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "base")

    def review(self, *extra):
        out = self.dir / "_out"
        args = ["review", "--repo", str(self.dir), "--json-out", str(out / "r.json"),
                "--md-out", str(out / "r.md"), "--quiet", *extra]
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cli.main(args)
        data = json.loads((out / "r.json").read_text(encoding="utf-8")) if (out / "r.json").exists() else None
        return code, data, err.getvalue()

    def ids(self, data):
        return sorted({f["rule_id"] for f in data["findings"]})


class TestChanges(RepoCase):
    def test_only_changed_lines_are_reported(self):
        self.write("app/src/main/resources/application.yml", "db:\n  password: oldSecret99\n")
        self.commit()
        # 기존 줄은 그대로 두고 아래에 무해한 줄만 추가
        self.write("app/src/main/resources/application.yml", "db:\n  password: oldSecret99\n  pool: 5\n")
        code, data, _ = self.review()
        self.assertEqual(code, 0)
        self.assertNotIn("SEC-001", self.ids(data))

    def test_new_secret_line_blocks_and_is_masked(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("conf/app.yml", "spring:\n  datasource:\n    password: Sup3rSecretValue\n")
        code, data, _ = self.review()
        self.assertEqual(code, 1)
        sec = [f for f in data["findings"] if f["rule_id"] == "SEC-001"]
        self.assertEqual(len(sec), 1)
        self.assertEqual(sec[0]["line"], 3)
        self.assertNotIn("Sup3rSecretValue", json.dumps(data, ensure_ascii=False))
        md = (self.dir / "_out" / "r.md").read_text(encoding="utf-8")
        self.assertNotIn("Sup3rSecretValue", md)
        self.assertIn("배포 보류 사유", md)

    def test_env_reference_is_not_a_secret(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("app.yml", "db:\n  password: ${DB_PASSWORD}\n  secret: ${APP_SECRET:}\n")
        _, data, _ = self.review()
        self.assertNotIn("SEC-001", self.ids(data))

    def test_placeholder_is_flagged_separately(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("app.yml", "admin:\n  password: change-me\n")
        _, data, _ = self.review()
        self.assertIn("SEC-002", self.ids(data))
        self.assertNotIn("SEC-001", self.ids(data))

    def test_repo_without_commits_reviews_everything(self):
        self.write("m/UserMapper.xml", "<select id=\"a\">SELECT a FROM t ORDER BY ${col}</select>\n")
        code, data, _ = self.review()
        self.assertEqual(code, 1)
        self.assertIn("SEC-006", self.ids(data))

    def test_mybatis_generator_condition_is_not_flagged(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("mbg/OrderMapper.xml",
                   "<when test=\"criterion.noValue\">and ${criterion.condition}</when>\n")
        _, data, _ = self.review()
        self.assertNotIn("SEC-006", self.ids(data))

    def test_mybatis_generator_order_by_is_still_flagged(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("mbg/OrderMapper.xml",
                   "<if test=\"orderByClause != null\">order by ${orderByClause}</if>\n")
        _, data, _ = self.review()
        self.assertIn("SEC-006", self.ids(data))

    def test_cp949_file_is_read(self):
        self.write("a.txt", "x\n")
        self.commit()
        p = self.dir / "legacy" / "Old.java"
        p.parent.mkdir(parents=True)
        p.write_bytes('// 한글 주석\nString password = "hardcoded123";\n'.encode("cp949"))
        _, data, _ = self.review()
        self.assertIn("SEC-005", self.ids(data))

    def test_bad_base_is_an_error(self):
        self.write("a.txt", "x\n")
        self.commit()
        code, data, err = self.review("--base", "no-such-branch")
        self.assertEqual(code, 2)
        self.assertIn("기준 리비전", err)


class TestRuleKinds(RepoCase):
    def test_test_counterpart_and_no_assert(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("svc/src/main/java/x/OrderService.java", "class OrderService {}\n")
        self.write("svc/src/main/java/x/PriceCalc.java", "class PriceCalc {}\n")
        self.write("svc/src/test/java/x/PriceCalcTest.java",
                   "class PriceCalcTest {\n"
                   "  @Test\n  void runs() {\n    new PriceCalc();\n  }\n"
                   "  @Test void checks() { assertEquals(1, 1); }\n"
                   "}\n")
        _, data, _ = self.review()
        tst1 = [f["file"] for f in data["findings"] if f["rule_id"] == "TST-001"]
        self.assertEqual(tst1, ["svc/src/main/java/x/OrderService.java"])
        tst2 = [f for f in data["findings"] if f["rule_id"] == "TST-002"]
        self.assertEqual([f["line"] for f in tst2], [3])

    def test_endpoint_coverage(self):
        self.write("e2e/smoke_e2e.py", "get('/api/orders/list')\n")
        self.commit()
        self.write("web/OrderController.java",
                   "@RequestMapping(\"/api/orders\")\n"
                   "public class OrderController {\n"
                   "  @GetMapping(\"/list\") public void list() {}\n"
                   "  @PostMapping(value = \"/save\") public void save() {}\n"
                   "}\n")
        _, data, _ = self.review()
        e2e = [f["snippet"] for f in data["findings"] if f["rule_id"] == "E2E-001"]
        self.assertEqual(len(e2e), 1)
        self.assertIn("/api/orders/save", e2e[0])

    def test_multiline_empty_catch(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("A.java", "class A {\n void f() {\n  try { g(); } catch (Exception e) {\n  }\n }\n}\n")
        _, data, _ = self.review()
        ux = [f for f in data["findings"] if f["rule_id"] == "UX-001"]
        self.assertEqual([f["line"] for f in ux], [3])

    def test_example_pack_and_duplicate_ids(self):
        rd = ROOT / "rules"
        rs = rules.load_packs(["core", "examples/layered-spring.toml"], rd)
        self.assertTrue(any(r.id == "EX-ARC-001" for r in rs))
        with self.assertRaises(ValueError):
            rules.load_packs(["core", "core"], rd)

    def test_pack_name_wins_over_same_named_cwd_folder(self):
        # 저장소 루트에 core/ 폴더(엔진)가 있어도 규칙팩 core 를 읽어야 한다.
        import os
        old = os.getcwd()
        os.chdir(ROOT)
        try:
            rs = rules.load_packs(["core"], ROOT / "rules")
        finally:
            os.chdir(old)
        self.assertGreater(len(rs), 20)
        self.assertTrue(all(r.pack.startswith("core/") for r in rs))

    def test_exclude_config(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write(".rulefirst.toml", 'exclude = ["**/generated/**"]\n')
        self.write("generated/app.yml", "password: Sup3rSecretValue\n")
        _, data, _ = self.review()
        self.assertNotIn("SEC-001", self.ids(data))


class TestFalsePositives(RepoCase):
    """시험 운용에서 나온 오탐을 고정한다."""

    def test_known_false_positives_stay_quiet(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("app.yml", "spring:\n  security:\n    password-parameter: password\n")
        self.write("src/test/java/x/RepoTest.java",
                   'class RepoTest {\n  void f() { sql("SELECT a FROM " + T + " WHERE x=?"); }\n}\n')
        self.write("src/main/java/x/Io.java",
                   "class Io {\n  void f() {\n    try { c.close(); } catch (Exception ignore) {\n    }\n  }\n}\n")
        self.write("src/test/java/x/SkipTest.java",
                   "class SkipTest {\n  /**\n   * 되살리려면 @Disabled 를 지운다\n   */\n}\n")
        _, data, _ = self.review()
        for rid in ("SEC-002", "SEC-007", "UX-001", "TST-003"):
            self.assertNotIn(rid, self.ids(data), rid)

    def test_real_ones_still_fire(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("src/main/java/x/Dao.java",
                   'class Dao {\n  void f(String id) { q("SELECT a FROM t WHERE id=" + id); }\n'
                   "  void g() { try { h(); } catch (Exception e) {} }\n}\n")
        self.write("src/test/java/x/OffTest.java", 'class OffTest {\n  @Disabled("flaky")\n  void t() {}\n}\n')
        self.write("app.yml", "admin:\n  password: change-me\n")
        _, data, _ = self.review()
        for rid in ("SEC-002", "SEC-007", "UX-001", "TST-003"):
            self.assertIn(rid, self.ids(data), rid)


class TestVerify(unittest.TestCase):
    LINES = ["class A {", "  void f(String id) {", '    jdbc.query("select * from t where id=" + id);', "  }", "}"]

    def test_exact_and_whitespace_insensitive(self):
        self.assertTrue(verify.quote_matches(self.LINES, 3, 'jdbc.query("select * from t where id="   + id);'))

    def test_nearby_line_is_ok_but_far_is_not(self):
        self.assertTrue(verify.quote_matches(self.LINES, 1, "jdbc.query("))
        self.assertFalse(verify.quote_matches(self.LINES * 3, 15, "class A {", window=1))

    def test_invented_quote_rejected(self):
        self.assertFalse(verify.quote_matches(self.LINES, 3, "Runtime.getRuntime().exec(cmd)"))
        self.assertFalse(verify.quote_matches(self.LINES, 3, "  "))

    def test_line_number_prefix_is_stripped(self):
        self.assertTrue(verify.quote_matches(self.LINES, 2, "    2|   void f(String id) {"))


class FakeModel(BaseHTTPRequestHandler):
    reply: dict = {}
    seen: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeModel.seen.append(body)
        out = json.dumps({"choices": [{"message": {"content": json.dumps(FakeModel.reply)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


class TestLlmLayer(RepoCase):
    def setUp(self):
        super().setUp()
        self.srv = HTTPServer(("127.0.0.1", 0), FakeModel)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.srv.server_port}/v1"
        FakeModel.seen = []

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_hallucinated_quote_is_dropped(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("web/Api.java",
                   "class Api {\n"
                   "  @PostMapping(\"/run\")\n"
                   "  public String run(String q) { return dao.exec(q); }\n"
                   "}\n")
        FakeModel.reply = {"items": [
            {"id": "S1", "hit": True, "line": 2, "quote": '@PostMapping("/run")', "why": "권한 확인 없음"},
            {"id": "S2", "hit": True, "line": 3, "quote": "Runtime.getRuntime().exec(q)", "why": "지어낸 근거"},
            {"id": "S9", "hit": True, "line": 3, "quote": "dao.exec(q)", "why": "없는 문항"},
            {"id": "S3", "hit": False, "line": 0, "quote": "", "why": ""},
        ]}
        code, data, err = self.review("--llm-endpoint", self.endpoint, "--llm-model", "tiny")
        llm_f = [f for f in data["findings"] if f["source"] == "llm"]
        self.assertEqual([f["rule_id"] for f in llm_f], ["LLM-S1"])
        self.assertEqual(data["llm"]["rejected_quote"], 1)
        self.assertEqual(data["llm"]["rejected_other"], 1)
        self.assertEqual(code, 1)  # S1 은 high
        req = FakeModel.seen[0]
        self.assertEqual(req["model"], "tiny")
        self.assertEqual(req["temperature"], 0)
        self.assertEqual(req["response_format"]["type"], "json_schema")
        self.assertIn("    2| ", req["messages"][1]["content"])

    def test_remote_endpoint_is_refused(self):
        with self.assertRaises(ValueError):
            llm.check_endpoint("https://api.example.com/v1", allow_remote=False)
        llm.check_endpoint("http://localhost:11434/v1", allow_remote=False)

    def test_unreachable_model_is_counted_not_fatal(self):
        self.write("a.txt", "x\n")
        self.commit()
        self.write("web/Api.java", "class Api { void f() {} }\n")
        code, data, _ = self.review("--llm-endpoint", "http://127.0.0.1:9/v1")
        self.assertEqual(data["llm"]["errors"], 1)
        self.assertEqual(code, 0)


class TestConfig(unittest.TestCase):
    def test_gmatch(self):
        self.assertTrue(config.gmatch("app.yml", ["*.yml"]))
        self.assertTrue(config.gmatch("a/b/app.yml", ["*.yml"]))
        self.assertTrue(config.gmatch("node_modules/x.js", ["**/node_modules/**"]))
        self.assertTrue(config.gmatch("src/main/java/A.java", ["**/src/main/java/**/*.java"]))
        self.assertFalse(config.gmatch("src/test/java/A.java", ["**/src/main/java/**/*.java"]))

    def test_excerpt_marks_gaps(self):
        lines = [f"l{i}" for i in range(1, 101)]
        text = llm.excerpt(lines, {10, 90}, context=2, max_chars=10000)
        self.assertIn("   10| l10", text)
        self.assertIn("   ...", text)
        self.assertNotIn("   50| ", text)


if __name__ == "__main__":
    unittest.main()
