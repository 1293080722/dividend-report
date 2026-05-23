#!/usr/bin/env python3
"""
使用 GitHub REST API 直接上传文件到仓库（无需 git）
支持中文路径、大文件分块、自动处理已有文件
"""
import os
import base64
import json
import urllib.request
import urllib.parse
from pathlib import Path

# ========== 配置 ==========
TOKEN = "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"
OWNER = "1293080722"
REPO = "dividend-report"
BRANCH = "main"
# =============================

HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "Content-Type": "application/json; charset=utf-8",
}

BASE_URL = f"https://api.github.com/repos/{OWNER}/{REPO}"

# 工作区根目录
WORKSPACE = Path("C:/Users/Administrator/WorkBuddy/2026-05-23-task-5")

# 排除列表
EXCLUDE_DIRS = {".workbuddy", "__pycache__", ".git", "node_modules", ".pytest_cache", "__pycache__", ".DS_Store"}
EXCLUDE_FILES = {"push_with_dulwich.py"}  # 排除推送脚本自身


def get_file_sha(path_in_repo):
    """获取文件在仓库中的 SHA（用于更新已有文件）"""
    url = f"{BASE_URL}/contents/{urllib.parse.quote(path_in_repo, safe='')}?ref={BRANCH}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # 文件不存在
        raise


def upload_file(local_path: Path, path_in_repo: str, commit_msg: str, is_binary: bool = False):
    """上传单个文件到 GitHub"""
    sha = get_file_sha(path_in_repo)
    
    with open(local_path, "rb") as f:
        content_bytes = f.read()
    
    if is_binary:
        content_b64 = base64.b64encode(content_bytes).decode("ascii")
    else:
        content_b64 = base64.b64encode(content_bytes).decode("ascii")
    
    payload = {
        "message": commit_msg,
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    
    url = f"{BASE_URL}/contents/{urllib.parse.quote(path_in_repo, safe='')}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="PUT")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            status = "更新" if sha else "新建"
            print(f"  ✅ {status}: {path_in_repo}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  ❌ 失败: {path_in_repo} — HTTP {e.code}: {error_body[:200]}")
        return False


def ensure_branch():
    """确保 main 分支存在（如果仓库为空则创建）"""
    # 检查仓库是否有内容
    url = f"{BASE_URL}/branches?per_page=100"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            branches = json.loads(resp.read())
            branch_names = [b["name"] for b in branches]
            if BRANCH in branch_names:
                print(f"分支 '{BRANCH}' 已存在")
                return
            # 有分支但没有 main，需要创建
            if branches:
                default_branch = branches[0]["name"]
                print(f"默认分支是 '{default_branch}'，创建 '{BRANCH}' 分支...")
                # 获取默认分支的 SHA
                ref_url = f"{BASE_URL}/git/refs/heads/{default_branch}"
                req2 = urllib.request.Request(ref_url, headers=HEADERS)
                with urllib.request.urlopen(req2, timeout=15) as resp2:
                    ref_data = json.loads(resp2.read())
                    sha = ref_data["object"]["sha"]
                # 创建 main 分支
                create_url = f"{BASE_URL}/git/refs"
                payload = {"ref": f"refs/heads/{BRANCH}", "sha": sha}
                data = json.dumps(payload).encode("utf-8")
                req3 = urllib.request.Request(create_url, data=data, headers=HEADERS, method="POST")
                with urllib.request.urlopen(req3, timeout=15) as resp3:
                    print(f"  ✅ 分支 '{BRANCH}' 创建成功")
                return
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"仓库为空，将通过首次提交自动创建分支 '{BRANCH}'")
            return
        raise


def collect_files():
    """收集需要上传的文件"""
    files = []
    for f in WORKSPACE.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(WORKSPACE)
        # 排除目录
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        # 排除文件
        if rel.name in EXCLUDE_FILES:
            continue
        files.append((f, str(rel).replace("\\", "/")))
    return files


def main():
    print(f"=== 推送到 GitHub: {OWNER}/{REPO} (branch: {BRANCH}) ===\n")
    
    # 确认分支
    ensure_branch()
    print()
    
    # 收集文件
    files = collect_files()
    print(f"发现 {len(files)} 个文件待上传：\n")
    
    success = 0
    for local_path, repo_path in files:
        ext = local_path.suffix.lower()
        is_binary = ext in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".zip", ".exe"}
        commit_msg = f"{'Add' if not get_file_sha(repo_path) else 'Update'}: {repo_path}"
        ok = upload_file(local_path, repo_path, commit_msg, is_binary)
        if ok:
            success += 1
    
    print(f"\n=== 完成：{success}/{len(files)} 个文件上传成功 ===")
    print(f"仓库地址：https://github.com/{OWNER}/{REPO}")


if __name__ == "__main__":
    main()
