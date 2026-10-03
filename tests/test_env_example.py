"""/etc/onulpan.env 견본은 systemd EnvironmentFile과 bash 양쪽에서 같은 값으로 읽혀야 한다."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
LINE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=("[^"$`]*"|[^\s"\'#$`]*)$')


def test_example_has_no_inline_comments():
    for n, line in enumerate(EXAMPLE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        assert LINE.match(line), f".env.example:{n}: {line!r} — 주석은 값 위 줄로, 공백 있는 값은 큰따옴표로"


def test_example_keys_unique():
    keys = [ln.split("=", 1)[0] for ln in EXAMPLE.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
    assert len(keys) == len(set(keys))


def test_check_env_script(tmp_path):
    script = ROOT / "infra" / "check-env.sh"
    assert subprocess.run([str(script), str(EXAMPLE)], capture_output=True).returncode == 0
    bad = tmp_path / "bad.env"
    bad.write_text("ONULPAN_ENV=production   # 설명\nSITE_URL=https://x\n", encoding="utf-8")
    assert subprocess.run([str(script), str(bad)], capture_output=True).returncode == 1
    assert subprocess.run([str(script), "--fix", str(bad)], capture_output=True).returncode == 0
    assert bad.read_text(encoding="utf-8") == "# 설명\nONULPAN_ENV=production\nSITE_URL=https://x\n"
    out = subprocess.run(["bash", "-c", f"set -a; . {bad}; set +a; printf %s \"$ONULPAN_ENV\""],
                         capture_output=True, text=True).stdout
    assert out == "production"


def test_restore_uses_bootstrap_ownership():
    """복원은 bootstrap과 같은 소유 구조(postgres)로. 없는 역할(onulpan)로 SET ROLE 하지 않는다."""
    text = (ROOT / "infra" / "restore.sh").read_text(encoding="utf-8")
    assert "--role" not in text and "REASSIGN OWNED" not in text
    assert "--single-transaction" in text and "--exit-on-error" in text and "--no-owner" in text
