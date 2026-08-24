"""Interactive user-management command for the deployed container."""

from __future__ import annotations

import argparse
import getpass

from app.auth import create_user, init_auth_database


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-admin", "create-user"])
    parser.add_argument("--username")
    args = parser.parse_args()
    init_auth_database()
    username = args.username or input("管理员用户名: " if args.command == "create-admin" else "用户名: ")
    first = getpass.getpass("密码: ")
    second = getpass.getpass("再次输入密码: ")
    if first != second:
        raise SystemExit("两次密码不一致")
    if len(first) < 12:
        raise SystemExit("密码至少需要 12 个字符")
    create_user(username.strip(), first, "admin" if args.command == "create-admin" else "user")
    print(f"用户 {username} 创建成功")


if __name__ == "__main__":
    main()
