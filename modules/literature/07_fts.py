"""07 全文检索: FTS5 索引 + 命令行查询.

  python3 07_fts.py <corpus> build                      重建索引 (01/02/04/05 改过 pages 后重跑)
  python3 07_fts.py <corpus> search '<查询>' [-n 20]    查询, 输出 文献 / 页码 / 片段

  pages_fts: 外部内容表 (content=pages, 不另存文本), unicode61 去变音 -> 西文按词;
             FTS5 语法: "Travisia forbesii" 短语, travis* 前缀, A AND B, A NOT B, NEAR(A B, 10)
  pages_cjk: 中日文页 (前 3000 字 CJK > 30) 另建 trigram 表 (unicode61 把整段汉字当一个词, 不可用);
             查询含 CJK 时走这里, 子串匹配, 至少 3 字
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import litdb  # noqa: E402
from common import summary  # noqa: E402

CJK = re.compile(r"[぀-ヿ一-鿿]")


def build(con):
    t0 = time.time()
    con.executescript("""
        DROP TABLE IF EXISTS pages_fts;
        CREATE VIRTUAL TABLE pages_fts USING fts5(text, content='pages', content_rowid='rowid',
                                                  tokenize='unicode61 remove_diacritics 2');
        INSERT INTO pages_fts(pages_fts) VALUES ('rebuild');
        INSERT INTO pages_fts(pages_fts) VALUES ('optimize');
        DROP TABLE IF EXISTS pages_cjk;
        CREATE VIRTUAL TABLE pages_cjk USING fts5(text, page_rowid UNINDEXED, tokenize='trigram');
    """)
    rows = ((t, rid) for rid, t in con.execute("SELECT rowid, text FROM pages WHERE text <> ''")
            if len(CJK.findall(t[:3000])) > 30)
    con.executemany("INSERT INTO pages_cjk (text, page_rowid) VALUES (?, ?)", list(rows))
    con.commit()
    n, n_cjk = con.execute("SELECT (SELECT count(*) FROM pages), (SELECT count(*) FROM pages_cjk)").fetchone()
    return [f"pages_fts 索引 {n} 页; pages_cjk (trigram) {n_cjk} 页; 用时 {time.time() - t0:.0f}s"]


def search(con, q, n):
    if CJK.search(q):
        sql = ("SELECT d.relpath, p.page_no, snippet(pages_cjk, 0, '[', ']', '…', 20) FROM pages_cjk"
               " JOIN pages p ON p.rowid = pages_cjk.page_rowid JOIN docs d USING (doc_id)"
               " WHERE pages_cjk MATCH ? ORDER BY rank LIMIT ?")
    else:
        sql = ("SELECT d.relpath, p.page_no, snippet(pages_fts, 0, '[', ']', '…', 16) FROM pages_fts"
               " JOIN pages p ON p.rowid = pages_fts.rowid JOIN docs d USING (doc_id)"
               " WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?")
    for rel, pn, snip in con.execute(sql, (q, n)):
        print(f"{rel}  p.{pn}\n    {re.sub(r'\s+', ' ', snip)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("step", choices=["build", "search"])
    ap.add_argument("query", nargs="?")
    ap.add_argument("-n", type=int, default=20)
    a = ap.parse_args()
    con = litdb.connect(a.corpus)
    if a.step == "build":
        lines = build(con)
        con.close()
        summary("07_fts build", lines + [f"备份 -> {litdb.backup(a.corpus)}"])
    else:
        search(con, a.query, a.n)


if __name__ == "__main__":
    main()
