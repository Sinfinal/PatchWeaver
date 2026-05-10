# PatchWeaver 部署说明

本文面向评委和验证机部署人员，说明如何在验证机上完成 PatchWeaver 的最小可用部署、环境自检、Web/API 启动和常见问题处理。文档只描述部署流程，不记录任何 IP、密码、API Key 或平台 Token。

## 1. 验证机前置条件

建议在目标内核所在的 Linux 验证机本地运行 PatchWeaver。构建后端当前按本机 `local` 模式工作，因此任务运行机、目标内核构建材料和 `kpatch-build` 应保持在同一台验证机上。

必备条件：

- Python `3.11+`，可创建虚拟环境并安装本项目依赖。
- 可访问 PatchWeaver 源码目录。
- 目标内核与验证机一致，例如 `uname -r` 应与 `config/system.yaml` 中 `default_kernel` 对齐。
- 已安装 `kpatch-build`，且命令在当前用户的 `PATH` 中可见。
- 已准备与目标内核匹配的源码树、`.config`、`Module.symvers` 和 `vmlinux`。
- 验证机磁盘空间足够容纳工作区、源码树缓存、构建产物和日志。
- 如需调用百炼/DashScope 模型，使用环境变量 `PATCHWEAVER_BAILIAN_API_KEY` 注入密钥，不写入仓库文件。

建议提前确认：

```bash
python3 --version
uname -r
which kpatch-build
test -f /usr/src/kernels/$(uname -r)/.config
test -f /usr/lib/debug/lib/modules/$(uname -r)/vmlinux
```

## 2. 快速部署命令

以下命令在 PatchWeaver 项目根目录执行。若验证机无法联网，请提前离线准备 Python wheel、Node 依赖和系统包。

```bash
cd /path/to/PatchWeaver
python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
python -m pip install -e .

python -m patchweaver init --with-db --json
python -m patchweaver doctor --json
```

如需 Web 控制台，先构建前端静态资源：

```bash
cd web
npm install
npm run build
cd ..
```

`web/dist` 存在时，后端会自动把控制台挂载到 `/console/`；不存在时，根路径会回退到 API 文档。

## 3. Dry-run 检查

部署后先做只读或低风险检查，确认环境问题和代码问题分开定位。

```bash
python -m patchweaver paths --json
python -m patchweaver models --json
python -m patchweaver doctor --json
python -m patchweaver check-vendor-baseline --json
```

检查结果重点看：

- `doctor.summary.error` 是否为 `0`。
- `external_command` 中 `kpatch-build` 是否为 `ok`。
- `build_env.selected_source_dir`、`build_env.config_path`、`build_env.vmlinux_path` 是否命中真实路径。
- `runtime.detected_target_kernel` 是否与预期目标内核一致。
- `models.api_key` 是否来自环境变量；若提示来自配置文件，应迁移到环境变量。

如果只想检查源码基线，不希望写回配置，可显式传入目标源码和补丁：

```bash
python -m patchweaver check-vendor-baseline \
  --source-dir /path/to/vendor-baseline \
  --target-kernel "$(uname -r)" \
  --patch /path/to/raw_patch.patch \
  --json
```

## 4. 目标内核、源码基线与 kpatch-build 检查

PatchWeaver 构建链路依赖三类材料同时一致：目标内核、未修复源码基线、`kpatch-build` 构建环境。

目标内核检查：

- `uname -r` 与 `config/system.yaml` 的 `default_kernel` 保持一致，或在创建任务时显式指定 `--kernel`。
- `config/build.yaml` 中 `kernel_devel_dir`、`vmlinux_path` 指向对应内核版本。
- 验证机不要混用不同内核版本的源码树、debug 包和 `Module.symvers`。

源码基线检查：

- 优先使用与目标发行版内核完全一致的未修复 vendor source baseline。
- 如已准备完整源码树，可登记到 `prepared_kernel_src_dir`；默认源码目录为 `/opt/kernel-src`。
- 若目标补丁已在当前源码树中存在，应切换到未修复源码树，或让自动源码树切换/反向补丁树机制处理。
- stable 父版本源码仅用于上下文不匹配或补丁状态对齐，不应直接等同于最终正向验收基线。

可用命令：

```bash
python -m patchweaver prepare-build-tree \
  --kernel-release "$(uname -r)" \
  --warm-target vmlinux \
  --warm-jobs 20 \
  --json

python -m patchweaver check-vendor-baseline \
  --source-dir /path/to/vendor-baseline \
  --target-kernel "$(uname -r)" \
  --json
```

`kpatch-build` 检查：

- `which kpatch-build` 能找到命令。
- 当前用户具备读取源码树、`.config`、`Module.symvers`、`vmlinux` 和写入工作区的权限。
- 如遇 `unsupported section change`、入口偏移或模块依赖问题，先查看 `doctor --json`、任务 `report` 和构建日志，不要直接宣称 Final 可成功。

## 5. Web/API 启动

临时前台启动，适合评委现场查看日志。监听地址请由现场环境变量提供，不要写入文档或提交记录：

```bash
export PATCHWEAVER_API_HOST="<现场监听地址>"
python -m patchweaver serve-api --host "$PATCHWEAVER_API_HOST" --port 18084 --foreground
```

Linux + systemd 验证机可安装常驻服务：

```bash
sudo -E .venv/bin/python -m patchweaver install-api-service \
  --host "$PATCHWEAVER_API_HOST" \
  --port 18084 \
  --service-name patchweaver-web \
  --json
```

服务检查：

```bash
curl http://localhost:18084/healthz
systemctl status patchweaver-web --no-pager
journalctl -u patchweaver-web -n 100 --no-pager
```

访问入口：

- API 文档：`/docs`
- 健康检查：`/healthz`
- Web 控制台：`/console/`

## 6. 常见失败处理

`kpatch-build` 未找到：

- 安装 kpatch 工具链，确认 `which kpatch-build` 有输出。
- 检查 systemd 服务使用的虚拟环境和交互 shell 是否一致。

源码目录不可用：

- 检查 `config/build.yaml` 中源码路径。
- 确认源码树包含目标补丁涉及的文件，并与目标内核版本一致。
- 优先使用 `check-vendor-baseline --json` 判断基线是否适合正向验收。

`.config`、`Module.symvers` 或 `vmlinux` 缺失：

- 安装对应目标内核的 `kernel-devel`、debug 符号包或从发行版源码包补齐。
- 不要用其他内核版本的文件临时代替。

补丁无法应用或提示 `target_already_patched`：

- 检查当前源码树是否已经包含修复。
- 切换到未修复 vendor baseline，或准备 stable 父版本 baseline 做上下文对齐。
- 任务报告中的失败归因优先于人工猜测。

API 服务启动失败：

- 先用 `--foreground` 前台启动查看错误。
- 检查端口占用、虚拟环境路径、工作目录和 systemd 日志。
- 若前端页面不可访问，确认 `web/dist` 已生成；API 仍可通过 `/docs` 验证。

模型调用失败：

- 确认 `PATCHWEAVER_BAILIAN_API_KEY` 已在运行进程环境中设置。
- 不要把密钥写入 `config/models.yaml`、日志、截图或部署文档。
- 如评审环境不允许外网访问，应提前说明模型调用受限，并保留本地环境检查与构建证据。

## 7. 安全注意事项

- 不在文档、README、配置文件、命令历史、日志截图中记录真实 IP、密码、API Key、Token 或 Cookie。
- 百炼/DashScope 密钥只通过环境变量或平台 Secret 注入。
- systemd 服务如需读取环境变量，使用受控的环境文件或平台 Secret，不把明文写入仓库。
- 构建和验证过程会生成内核模块、日志和报告，应限制工作区目录权限。
- 对外开放 Web/API 前应加访问控制、网络隔离或反向代理鉴权；默认接口不等同于公网安全服务。
- PatchWeaver 会尽力给出构建、失败归因和报告证据，但具体 CVE 是否最终生成可加载 livepatch 取决于补丁形态、源码基线、kpatch 支持范围和验证机环境，不应承诺固定 Final 成功率。
