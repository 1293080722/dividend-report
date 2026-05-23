# 红利组合日报 - GitHub Actions 部署指南

## 你只需要做 3 步

### 第 1 步：创建 GitHub 仓库

1. 打开 https://github.com/new
2. Repository name 填：`dividend-report`（或其他喜欢的名字）
3. 选 **Private**（私有仓库，只有你能看到）
4. 点击 **Create repository**

### 第 2 步：设置 Secrets（邮件密钥）

1. 进入仓库 → Settings → Secrets and variables → Actions
2. 点击 **New repository secret**，添加以下 3 个：

| Secret 名称 | 值 |
|-------------|-----|
| `DIV_EMAIL_FROM` | `1293080722@qq.com` |
| `DIV_EMAIL_TO` | `1293080722@qq.com` |
| `DIV_SMTP_PASS` | 你的QQ邮箱16位授权码 |

### 第 3 步：推送代码

在本地终端（PowerShell）依次执行：

```powershell
cd C:\Users\Administrator\WorkBuddy\2026-05-23-task-5\dividend-report

git init
git add .
git commit -m "红利组合日报 v1.0"
git branch -M main
git remote add origin https://github.com/1293080722/dividend-report.git
git push -u origin main
```

> ⚠️ 推送时可能需要输入GitHub用户名和token（不是密码，是Personal Access Token）

## 验证

推送成功后：
1. 进入仓库 → **Actions** 标签页
2. 找到 `红利组合日报` workflow
3. 点击 **Run workflow** → 手动触发一次测试
4. 检查是否收到邮件

## 工作原理

```
每个工作日 9:30（北京时间）
     ↓
GitHub Actions 自动启动
     ↓
Python 脚本运行（akshare抓数据 → 计算估值 → 生成HTML）
     ↓
通过QQ邮箱SMTP发送到 1293080722@qq.com
     ↓
报告也保存在仓库里（可回溯历史）
```

电脑关机也无所谓，全在云端跑。
