"""把当前项目快照上传到验证机。"""

from __future__ import annotations

import argparse
import getpass
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
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
    build_frontend: bool = True
    install_remote_runtime: bool = True
    run_remote_smoke_check: bool = True
    remote_python: str = "python3"
    remote_venv_name: str = ".venv"
    remote_smoke_port: int = 18084


class ValidationUploader:
    """负责打包本地代码并同步到验证机。"""

    def __init__(self, config: UploadConfig) -> None:
        """保存上传配置。"""

        self.config = config

    def run(self) -> None:
        """执行打包、上传和验证机目录展开。"""

        step_total = 6
        if self.config.build_frontend:
            self._build_frontend()
            print(f"[1/{step_total}] 前端构建完成 -> {self._web_dist_dir()}")
        else:
            print(f"[1/{step_total}] 已跳过前端构建，沿用现有 dist -> {self._web_dist_dir()}")

        archive_path, file_count = self._build_archive()
        remote_archive = PurePosixPath("/root") / archive_path.name

        print(f"[2/{step_total}] 已打包本地项目，共 {file_count} 个条目")
        print(f"      {archive_path}")

        client = self._connect()
        try:
            print(f"[3/{step_total}] 已连接验证机 {self.config.username}@{self.config.host}:{self.config.port}")
            self._upload_archive(client, archive_path=archive_path, remote_archive=remote_archive)
            print(f"[4/{step_total}] 上传完成 -> {remote_archive}")
            self._extract_archive(client, remote_archive=remote_archive)
            print(f"[5/{step_total}] 验证机目录已更新 -> {self.config.remote_dir}")
            if self.config.install_remote_runtime:
                self._install_remote_runtime(client)
                print(f"[6/{step_total}] 验证机运行时安装完成")
            else:
                print(f"[6/{step_total}] 已跳过验证机运行时安装")
            if self.config.run_remote_smoke_check:
                self._run_remote_smoke_check(client)
                print("      验证机 API / Web 冒烟检查通过")
            else:
                print("      已跳过验证机冒烟检查")
            print("      可在验证机上继续执行:")
            print(f"      cd {self.config.remote_dir}")
            print(f"      source {self._remote_venv_dir().as_posix()}/bin/activate")
            print("      systemctl status patchweaver-web --no-pager")
            print(f"      curl http://127.0.0.1:{self.config.remote_smoke_port}/healthz")
        finally:
            client.close()

    def _build_frontend(self) -> None:
        """先在本地构建前端，确保 dist 会随项目一起上传。"""

        web_dir = self.config.project_root / "web"
        if not (web_dir / "package.json").exists():
            raise RuntimeError(f"未找到前端工程目录：{web_dir}")

        npm_command = shutil.which("npm.cmd") or shutil.which("npm")
        if npm_command is None:
            raise RuntimeError("当前环境未找到 npm，可先安装 Node.js 或手动完成 web/dist 构建。")

        command = [npm_command, "run", "build"]
        completed = subprocess.run(
            command,
            cwd=web_dir,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "本地前端构建失败:\n"
                f"command: {' '.join(command)}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        dist_dir = self._web_dist_dir()
        if not dist_dir.exists():
            raise RuntimeError(f"前端构建完成后仍未找到 dist 目录：{dist_dir}")

    def _web_dist_dir(self) -> Path:
        """返回本地前端构建产物目录。"""

        return (self.config.project_root / "web" / "dist").resolve()

    def _remote_venv_dir(self) -> PurePosixPath:
        """返回验证机上的虚拟环境目录。"""

        return self.config.remote_dir / self.config.remote_venv_name

    def _build_archive(self) -> tuple[Path, int]:
        """在临时目录中生成一份可上传的压缩包。"""

        temp_dir = Path(tempfile.mkdtemp(prefix="patchweaver-upload-"))
        archive_path = temp_dir / f"patchweaver_validate_{time.strftime('%Y%m%d_%H%M%S')}.tar.gz"
        root_name = self.config.project_root.name
        file_count = 0

        with tarfile.open(archive_path, mode="w:gz", compresslevel=6) as tar:
            # 目录也一起收进去，验证机解压后目录结构会更完整。
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
        """建立到验证机的连接。"""

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
                (
                    f"find {shlex.quote((remote_dir / 'web' / 'dist').as_posix())} "
                    "-maxdepth 2 -type f | sort | head -n 20"
                ),
            ]
        )

        if not self.config.keep_remote_archive:
            commands.append(f"rm -f {shlex.quote(remote_archive.as_posix())}")

        for command in commands:
            stdout_text, stderr_text, exit_code = self._run_remote_command(client, command)
            if exit_code != 0:
                raise RuntimeError(
                    "验证机执行失败:\n"
                    f"command: {command}\n"
                    f"stdout:\n{stdout_text}\n"
                    f"stderr:\n{stderr_text}"
                )
            if "find " in command:
                print("      验证机文件预览:")
                if stdout_text.strip():
                    for line in stdout_text.strip().splitlines():
                        print(f"      {line}")

    def _install_remote_runtime(self, client: paramiko.SSHClient) -> None:
        """在验证机上安装 Python 运行时依赖，并初始化最小环境。"""

        remote_dir = self.config.remote_dir.as_posix()
        remote_venv = self._remote_venv_dir().as_posix()
        remote_python = shlex.quote(self.config.remote_python)
        api_port = self.config.remote_smoke_port

        install_script = textwrap.dedent(
            f"""
            set -e
            cd {shlex.quote(remote_dir)}

            PYTHON_BIN=""
            for candidate in {remote_python} /usr/bin/python3 python3 python; do
              if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then
                if "$candidate" -c "mods = ['paramiko', 'fastapi', 'uvicorn', 'typer', 'pydantic', 'yaml', 'jinja2', 'unidiff', 'rich']; [__import__(name) for name in mods]" >/dev/null 2>&1; then
                  PYTHON_BIN="$candidate"
                  break
                fi
              fi
            done

            if [ -z "$PYTHON_BIN" ]; then
              echo "未找到带项目依赖的 Python 解释器" >&2
              exit 1
            fi

            rm -rf {shlex.quote(remote_venv)}
            "$PYTHON_BIN" -m venv --system-site-packages {shlex.quote(remote_venv)}
            SITE_PACKAGES=$({shlex.quote(remote_venv)}/bin/python -c "import site; candidates = [item for item in site.getsitepackages() if item.endswith('site-packages')]; print(candidates[0] if candidates else (_ for _ in ()).throw(SystemExit('未找到 site-packages 目录')))") 
            printf '%s\n' {shlex.quote(remote_dir)} > "$SITE_PACKAGES/patchweaver_validate_current.pth"
            printf '%s\n' \
              '#!/usr/bin/env bash' \
              'set -e' \
              'ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"' \
              'export PATCHWEAVER_API_HOST="${{PATCHWEAVER_API_HOST:-0.0.0.0}}"' \
              'export PATCHWEAVER_API_PORT="${{PATCHWEAVER_API_PORT:-{api_port}}}"' \
              'exec "$ROOT_DIR/.venv/bin/python" -m patchweaver.api' \
              > {shlex.quote((self.config.remote_dir / 'scripts' / 'run_validation_api.sh').as_posix())}
            chmod +x {shlex.quote((self.config.remote_dir / 'scripts' / 'run_validation_api.sh').as_posix())}

            {shlex.quote(remote_venv)}/bin/python -m patchweaver init-db
            {shlex.quote(remote_venv)}/bin/python -m patchweaver install-api-service --service-name patchweaver-web --host 0.0.0.0 --port {api_port}
            {shlex.quote(remote_venv)}/bin/python -c "from pathlib import Path; from patchweaver.api.app import app; required_routes = {{'/', '/healthz', '/api/v1/overview', '/api/v1/tasks', '/api/v1/reports/tasks/{{task_id}}', '/api/v1/evaluations/groups'}}; route_paths = {{getattr(route, 'path', '') for route in app.routes}}; missing = sorted(required_routes - route_paths); dist_dir = Path('web/dist'); missing and (_ for _ in ()).throw(SystemExit(f'缺少接口路由: {{missing}}')); (not dist_dir.exists()) and (_ for _ in ()).throw(SystemExit(f'未找到前端构建产物: {{dist_dir.resolve()}}')); print('validation install ok'); print(f'dist: {{dist_dir.resolve()}}'); print('launcher: scripts/run_validation_api.sh')"
            """
        ).strip()

        stdout_text, stderr_text, exit_code = self._run_remote_shell_script(client, install_script, timeout=1800)
        if exit_code != 0:
            raise RuntimeError(
                "验证机安装失败:\n"
                f"stdout:\n{stdout_text}\n"
                f"stderr:\n{stderr_text}"
            )
        if stdout_text.strip():
            print("      验证机安装输出:")
            for line in stdout_text.strip().splitlines():
                print(f"      {line}")

    def _run_remote_smoke_check(self, client: paramiko.SSHClient) -> None:
        """验证已安装的验证机 API 服务，并检查健康检查和控制台页面。"""

        remote_dir = self.config.remote_dir.as_posix()
        port = self.config.remote_smoke_port

        smoke_script = textwrap.dedent(
            f"""
            set -e
            cd {shlex.quote(remote_dir)}
            systemctl is-active patchweaver-web >/dev/null

            {shlex.quote(self._remote_venv_dir().as_posix())}/bin/python - <<'PY'
            import json
            import urllib.request

            health = urllib.request.urlopen("http://127.0.0.1:{port}/healthz", timeout=5)
            health_payload = json.loads(health.read().decode("utf-8"))
            if health_payload.get("status") != "ok":
                raise SystemExit(f"healthz 返回异常: {{health_payload}}")

            console = urllib.request.urlopen("http://127.0.0.1:{port}/console/", timeout=5)
            html = console.read().decode("utf-8", "ignore")
            if "PatchWeaver" not in html and "<!doctype html" not in html.lower():
                raise SystemExit("控制台首页内容异常")

            print("healthz ok")
            print("console ok")
            PY
            """
        ).strip()

        stdout_text, stderr_text, exit_code = self._run_remote_shell_script(client, smoke_script, timeout=300)
        if exit_code != 0:
            raise RuntimeError(
                "验证机冒烟检查失败:\n"
                f"stdout:\n{stdout_text}\n"
                f"stderr:\n{stderr_text}"
            )
        if stdout_text.strip():
            print("      验证机冒烟输出:")
            for line in stdout_text.strip().splitlines():
                print(f"      {line}")

    def _run_remote_shell_script(
        self,
        client: paramiko.SSHClient,
        script: str,
        *,
        timeout: int,
    ) -> tuple[str, str, int]:
        """通过 bash -lc 执行一段验证机脚本。"""

        command = f"bash -lc {shlex.quote(script)}"
        return self._run_remote_command(client, command, timeout=timeout)

    def _run_remote_command(
        self,
        client: paramiko.SSHClient,
        command: str,
        *,
        timeout: int = 300,
    ) -> tuple[str, str, int]:
        """执行一条验证机命令并返回输出。"""

        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdout_text = stdout.read().decode("utf-8", "ignore")
        stderr_text = stderr.read().decode("utf-8", "ignore")
        exit_code = stdout.channel.recv_exit_status()
        return stdout_text, stderr_text, exit_code


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    env_host = os.getenv("PATCHWEAVER_VALIDATION_HOST", "10.223.185.3")
    env_port = int(os.getenv("PATCHWEAVER_VALIDATION_PORT", "22"))
    env_user = os.getenv("PATCHWEAVER_VALIDATION_USER", "root")
    env_remote_dir = os.getenv(
        "PATCHWEAVER_VALIDATION_TARGET_DIR",
        os.getenv("PATCHWEAVER_VALIDATION_REMOTE_DIR", "/root/patchweaver_validate_current"),
    )

    parser = argparse.ArgumentParser(description="把当前 PatchWeaver 代码上传到验证机。")
    parser.add_argument("--host", default=env_host, help="验证机地址。")
    parser.add_argument("--port", type=int, default=env_port, help="验证机连接端口。")
    parser.add_argument("--user", default=env_user, help="验证机登录用户。")
    parser.add_argument(
        "--target-dir",
        "--remote-dir",
        dest="remote_dir",
        default=env_remote_dir,
        help="验证机展开目录。默认覆盖当前验证目录。",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("PATCHWEAVER_VALIDATION_PASSWORD"),
        help="验证机连接密码。默认优先读取环境变量 PATCHWEAVER_VALIDATION_PASSWORD。",
    )
    parser.add_argument(
        "--keep-remote-archive",
        action="store_true",
        help="保留验证机临时压缩包，方便后续排查。",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="解压前不清空验证机目录。",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="跳过本地 npm run build，直接上传现有前端产物。",
    )
    parser.add_argument(
        "--skip-target-install",
        "--skip-remote-install",
        dest="skip_remote_install",
        action="store_true",
        help="上传后不在验证机上创建虚拟环境和安装依赖。",
    )
    parser.add_argument(
        "--skip-target-smoke",
        "--skip-remote-smoke",
        dest="skip_remote_smoke",
        action="store_true",
        help="跳过验证机 API 与控制台的冒烟检查。",
    )
    parser.add_argument(
        "--target-python",
        "--remote-python",
        dest="remote_python",
        default=os.getenv("PATCHWEAVER_VALIDATION_TARGET_PYTHON", os.getenv("PATCHWEAVER_VALIDATION_REMOTE_PYTHON", "python3")),
        help="验证机优先使用的 Python 命令。默认 python3。",
    )
    parser.add_argument(
        "--target-venv-name",
        "--remote-venv-name",
        dest="remote_venv_name",
        default=os.getenv("PATCHWEAVER_VALIDATION_TARGET_VENV", os.getenv("PATCHWEAVER_VALIDATION_REMOTE_VENV", ".venv")),
        help="验证机上的虚拟环境目录名。默认 .venv。",
    )
    parser.add_argument(
        "--target-smoke-port",
        "--remote-smoke-port",
        dest="remote_smoke_port",
        type=int,
        default=int(os.getenv("PATCHWEAVER_VALIDATION_TARGET_SMOKE_PORT", os.getenv("PATCHWEAVER_VALIDATION_SMOKE_PORT", "18084"))),
        help="验证机冒烟检查时临时启动 API 的端口。",
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
        build_frontend=not args.skip_frontend_build,
        install_remote_runtime=not args.skip_remote_install,
        run_remote_smoke_check=not args.skip_remote_smoke,
        remote_python=args.remote_python,
        remote_venv_name=args.remote_venv_name,
        remote_smoke_port=args.remote_smoke_port,
    )

    uploader = ValidationUploader(config)
    uploader.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
