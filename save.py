import subprocess


def run(*a):
    return subprocess.run(a, capture_output=True, text=True)


run("git", "config", "user.name", "gongmae-bot")
run("git", "config", "user.email", "bot@users.noreply.github.com")
run("git", "add", "docs", "cache")
if run("git", "diff", "--cached", "--quiet").returncode == 0:
    print("no changes")
else:
    print(run("git", "commit", "-m", "daily update").stdout)
    r = run("git", "push")
    print(r.stdout, r.stderr)
    if r.returncode != 0:
        raise SystemExit("push failed")
