"""sra 模块测试公共件: 假 HTTP 传输、按文件名加载步骤脚本、临时项目."""
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

SRA = Path(__file__).resolve().parents[1]
ROOT = SRA.parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SRA))
sys.path.insert(0, str(ROOT / "lib"))

TAXON = "_test_sra"


def load_step(name):
    """modules/sra/01_runinfo.py 之类以数字开头的脚本无法直接 import."""
    spec = importlib.util.spec_from_file_location(f"sra_{name}", SRA / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeTransport:
    """rules: [(url 子串, 响应体或 callable(url)->str)], 按顺序取第一个匹配; 记录全部请求."""

    def __init__(self, rules):
        self.rules = rules
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        for key, body in self.rules:
            if key in url:
                return body(url) if callable(body) else body
        raise AssertionError(f"unexpected url {url}")


def fake_eutils(rules):
    from eutils import Eutils
    t = FakeTransport(rules)
    return Eutils(transport=t, sleep=lambda s: None), t


@pytest.fixture
def project():
    d = ROOT / "projects" / TAXON
    shutil.rmtree(d, ignore_errors=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
