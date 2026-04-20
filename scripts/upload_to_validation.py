"""把当前项目快照上传到验证机。"""

from __future__ import annotations

import argparse
import getpass
import os
import shlex
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import paramiko


EXCLUDED_TOP_LEVEL = {
    ".git",
    ".idea",
    ".jbeval",
    ".pytest_tmp",
    ".venv",
    "data",
    "workspaces",
}

EXCLUDED_PARTS = {
    "__pycache__",
    "node_modules",
}

EXCLUDED_RELATIVE_ROOTS = {
    Path("tests") / "_tmp",
}

EXCLUDED_SUFFIXES = {
    ".db",
    ".log",
}


@dataclass(slots=True)
class UploadConfig:
    """保存一次上传任务的配置。"""

    project_root: Path
    host: str
    port: int
    username: str
    password: str
    remote_dir: PurePosixPath
    keep_remote_archive: bool = False
    clean_remote_dir: bool = True


class ValidationUploader:
    """负责打包本地代码并同步到验证机。"""

    def __init__(self, config: UploadConfig) -> None:
        """保存上传配置。"""

        self.config = config

    def run(self) -> None:
        """执行打包、上传和远端展开。"""

        archive_path, file_count = self._build_archive()
        remote_archive = PurePosixPath("/root") / archive_path.name

        print(f"[1/4] 已打包本地项目，共 {file_count} 个条目")
        print(f"      {archive_path}")

        client = self._connect()
        try:
            print(f"[2/4] 已连接验证机 {self.config.username}@{self.config.host}:{self.config.port}")
            self._upload_archive(client, archive_path=archive_path, remote_archive=remote_archive)
            print(f"[3/4] 上传完成 -> {remote_archive}")
            self._extract_archive(client, remote_archive=remote_archive)
            print(f"[4/4] 远端目录已更新 -> {self.config.remote_dir}")
            print("      可在验证机上继续执行:")
            print(f"      cd {self.config.remote_dir}")
        finally:
            client.close()

    def _build_archive(self) -> tuple[Path, int]:
        """在临时目录中生成一份可上传的压缩包。"""

        temp_dir = Path(tempfile.mkdtemp(prefix="patchweaver-upload-"))
        archive_path = temp_dir / f"patchweaver_validate_{time.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        root_name = self.config.project_root.name
        file_count = 0

        with tarfile.open(archive_path, mode="w:gz", compresslevel=6) as tar:
            # 目录也一起收进去，远端解压后目录结构会更完整。
            for path in sorted(self.config.project_root.rglob("*")):
                relative_path = path.relative_to(self.config.project_root)
                if self._should_skip(relative_path):
                    continue
                try:
                    path.lstat()
                except OSError:
                    continue
                tar.add(path, arcname=str(Path(root_name) / relative_path), recursive=False)
                file_count += 1

        return archive_path, file_count

    def _should_skip(self, relative_path: Path) -> bool:
        """判断某个相对路径是否需要排除。"""

        if not relative_path.parts:
            return False

        if relative_path.parts[0] in EXCLUDED_TOP_LEVEL:
            return True

        if any(part in EXCLUDED_PARTS for part in relative_path.parts):
            return True

        if any(
            relative_path == excluded_root or excluded_root in relative_path.parents
            for excluded_root in EXCLUDED_RELATIVE_ROOTS
        ):
            return True

        if relative_path.suffix.lower() in EXCLUDED_SUFFIXES:
            return True

        return False

    def _connect(self) -> paramiko.SSHClient:
        """建立到验证机的 SSH 连接。"""

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
            timeout=20,
        )
        return client

    def _upload_archive(self, client: paramiko.SSHClient, *, archive_path: Path, remote_archive: PurePosixPath) -> None:
        """通过 SFTP 上传压缩包。"""

        sftp = client.open_sftp()
        try:
            sftp.put(str(archive_path), remote_archive.as_posix())
        finally:
            sftp.close()

    def _extract_archive(self, client: paramiko.SSHClient, *, remote_archive: PurePosixPath) -> None:
        """在验证机上清理并展开上传包。"""

        remote_dir = self.config.remote_dir
        commands: list[str] = []

        if self.config.clean_remote_dir:
            commands.append(f"rm -rf {shlex.quote(remote_dir.as_posix())}")

        commands.extend(
            [
                f"mkdir -p {shlex.quote(remote_dir.as_posix())}",
                (
                    f"tar -xzf {shlex.quote(remote_archive.as_posix())} "
                    f"-C {shlex.quote(remote_dir.as_posix())} --strip-components=1"
                ),
                f"find {shlex.quote(remote_dir.as_posix())} -maxdepth 2 -type f | sort | head -n 40",
            ]
        )

        if not self.config.keep_remote_archive:
            commands.append(f"rm -f {shlex.quote(remote_archive.as_posix())}")

        for command in commands:
            stdout_text, stderr_text, exit_code = self._run_remote_command(client, command)
            if exit_code != 0:
                raise RuntimeError(
                    "远端执行失败:\n"
                    f"command: {command}\n"
                    f"stdout:\n{stdout_text}\n"
                    f"stderr:\n{stderr_text}"
                )
            if "find " in command:
                print("      远端文件预览:")
                if stdout_text.strip():
                    for line in stdout_text.strip().splitlines():
                        print(f"      {line}")

    def _run_remote_command(self, client: paramiko.SSHClient, command: str) -> tuple[str, str, int]:
        """执行一条远端命令并返回输出。"""

        stdin, stdout, stderr = client.exec_command(command, timeout=300)
        stdout_text = stdout.read().decode("utf-8", "ignore")
        stderr_text = stderr.read().decode("utf-8", "ignore")
        exit_code = stdout.channel.recv_exit_status()
        return stdout_text, stderr_text, exit_code


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    env_host = os.getenv("PATCHWEAVER_VALIDATION_HOST", "10.223.185.3")
    env_port = int(os.getenv("PATCHWEAVER_VALIDATION_PORT", "22"))
    env_user = os.getenv("PATCHWEAVER_VALIDATION_USER", "root")
    env_remote_dir = os.getenv("PATCHWEAVER_VALIDATION_REMOTE_DIR", "/root/patchweaver_validate_current")

    parser = argparse.ArgumentParser(description="把当前 PatchWeaver 代码上传到验证机。")
    parser.add_argument("--host", default=env_host, help="验证机地址。")
    parser.add_argument("--port", type=int, default=env_port, help="SSH 端口。")
    parser.add_argument("--user", default=env_user, help="SSH 登录用户。")
    parser.add_argument(
        "--remote-dir",
        default=env_remote_dir,
        help="远端展开目录。默认覆盖当前验证目录。",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("PATCHWEAVER_VALIDATION_PASSWORD"),
        help="SSH 密码。默认优先读取环境变量 PATCHWEAVER_VALIDATION_PASSWORD。",
    )
    parser.add_argument(
        "--keep-remote-archive",
        action="store_true",
        help="保留远端临时压缩包，方便后续排查。",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="解压前不清空远端目录。",
    )
    return parser


def discover_project_root() -> Path:
    """根据脚本位置回推项目根目录。"""

    return Path(__file__).resolve().parents[1]


def resolve_password(cli_password: str | None, *, username: str, host: str) -> str:
    """优先读取参数或环境变量，缺失时回退到交互输入。"""

    if cli_password:
        return cli_password
    return getpass.getpass(f"请输入 {username}@{host} 的密码: ")


def main() -> int:
    """脚本入口。"""

    parser = build_parser()
    args = parser.parse_args()

    config = UploadConfig(
        project_root=discover_project_root(),
        host=args.host,
        port=args.port,
        username=args.user,
        password=resolve_password(args.password, username=args.user, host=args.host),
        remote_dir=PurePosixPath(args.remote_dir),
        keep_remote_archive=args.keep_remote_archive,
        clean_remote_dir=not args.no_clean,
    )

    uploader = ValidationUploader(config)
    uploader.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
