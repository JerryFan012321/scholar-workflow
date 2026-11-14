#!/usr/bin/env python3
"""Prepare one synthetic, file-native design example; never contact a remote host."""

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

RUNNER = r'''#!/usr/bin/env python3
"""Synthetic line-estimation example. Standard library only; no remote access."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import struct
import subprocess
import sys

def fit(points, method):
    if method == "median":
        slope = statistics.median((b[1]-a[1])/(b[0]-a[0]) for i,a in enumerate(points) for b in points[i+1:])
        return slope, statistics.median(y-slope*x for x,y in points)
    mx = statistics.mean(x for x,y in points)
    my = statistics.mean(y for x,y in points)
    slope = sum((x-mx)*(y-my) for x,y in points)/sum((x-mx)**2 for x,y in points)
    return slope, my-slope*mx

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["show", "measure"])
    parser.add_argument("--recipe", action="append", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    recipes = [(p,json.loads((root/p).read_text())) for p in args.recipe]
    for _,c in recipes:
        assert c["n"] >= 2 and c["method"] in ("least-squares", "median")
        assert c["seeds"] and c["noise_std"] >= 0
    if args.action == "show":
        print(json.dumps(dict(recipes),ensure_ascii=False,indent=2)); return
    if not args.output:
        parser.error("measure requires --output")
    out = root/args.output
    out.mkdir(parents=True,exist_ok=False)
    start = datetime.now(timezone.utc).isoformat()
    commit = subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    rows=[]; provenance=[]
    for path,c in recipes:
        for seed in c["seeds"]:
            rng=random.Random(seed)
            xs=[-1+2*i/(c["n"]-1) for i in range(c["n"])]
            points=[(x,2*x+1+rng.gauss(0,c["noise_std"])+(c["outlier_shift"] if i%8==0 else 0)) for i,x in enumerate(xs)]
            a,b=fit(points,c["method"])
            error=statistics.mean(abs(a*x+b-(2*x+1)) for x in [-1+2*i/100 for i in range(101)])
            rows.append({"variant":c["name"],"seed":seed,"n":c["n"],"method":c["method"],"mae":error,"slope":a,"intercept":b})
        provenance.append({"recipe":path,"git_revision":commit,"recipe_sha256":hashlib.sha256((root/path).read_bytes()).hexdigest(),"effective":c})
    with (out/"measurements.csv").open("w") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    record={"synthetic":True,"started_at":start,"finished_at":datetime.now(timezone.utc).isoformat(),"exit_code":0,"python":platform.python_version(),"entry":sys.argv[1:],"recipes":provenance,"input_definition":"y=2x+1; seeded Gaussian observation noise; optional every-eighth-point positive outlier; test is 101 clean points on [-1,1]"}
    (out/"execution.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    (root/"models").mkdir(exist_ok=True)
    (root/"models"/"last-fit.bin").write_bytes(struct.pack("dd",a,b))
    (root/".build").mkdir(exist_ok=True)
    (root/".build"/"plot-coordinates.tmp").write_bytes(b"regenerable coordinates\n"*512)
    print(json.dumps({"result":args.output,"measurements":len(rows)}))

if __name__ == "__main__":
    main()
'''


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def json_file(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def git(root, *args):
    return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-c",
        "commit.gpgSign=false", "-c", "user.name=Scholar Workflow Example", "-c",
        "user.email=example@invalid", "-C", str(root), *args], text=True).strip()


def commit(root, message):
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", message)
    return git(root, "rev-parse", "HEAD")


def init_git(root):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "--quiet", "--initial-branch=codex/experiment-example")


def run_measure(root, group):
    subprocess.run([sys.executable, str(root / "run.py"), "measure", "--recipe",
        "recipes/baseline.json", "--recipe", "recipes/variant.json", "--output", f"results/{group}"], check=True)


def plot_and_summarize(root, group, title, common, difference):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Times New Roman"
    import statistics
    result = root / "results" / group
    with (result / "measurements.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    variants = list(dict.fromkeys(row["variant"] for row in rows))
    values = [[float(r["mae"]) for r in rows if r["variant"] == v] for v in variants]
    means = [statistics.mean(v) for v in values]
    fig, ax = plt.subplots(figsize=(6.2, 3.3), layout="constrained")
    colors = ["#5279a6", "#65a68f"]
    labels = ["8 observations", "32 observations"] if root.name == "sample-count" else ["Least squares", "Median slopes"]
    ax.bar(labels, means, color=colors, width=.48)
    for i, (vs, mean) in enumerate(zip(values, means)):
        ax.scatter([i + ((j % 5) - 2)*.035 for j in range(len(vs))], vs, color="#234059", s=12, alpha=.6)
        ax.text(i, max(vs)+.015, f"mean {mean:.4f}", ha="center", fontsize=11)
    ax.set_ylabel("Prediction MAE (lower is better)")
    ax.set_title("Synthetic data · matched conditions", loc="left", fontsize=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, max(max(v) for v in values)*1.25+.025)
    ax.grid(axis="y", alpha=.18)
    fig.savefig(result / "comparison.png", dpi=160)
    plt.close(fig)
    count = len(values[0])
    names = ["基准条件", "对照条件"]
    table = "\n".join(f"| {names[i]} | {common} | {difference[i]} | {means[i]:.4f} | {count} |" for i in range(2))
    better = names[means.index(min(means))]
    write(result / "RESULTS.md", f"""# {title}

这是用于审阅管理设计的合成实验。结果由附带脚本实际计算，不代表真实研究项目的结论。

在本次观测中，{better}的平均预测误差较低。图中柱高为均值，每个点为一次独立噪声采样的结果。

![两种条件的预测误差](comparison.png)

| 条件 | 相同部分 | 不同部分 | 预测 MAE（越低越好） | 噪声采样次数 |
|---|---|---|---:|---:|
{table}

输入由直线 y = 2x + 1 加观测噪声生成。拟合器根据带噪观测估计斜率和截距；
随后在同一组 101 个无噪声位置上预测，与已知真值比较。MAE 是预测值和真值之差的绝对值均值，
本例的 y 没有物理单位。它回答“拟合出的关系偏离真值多少”，并不测量运行速度或真实数据的泛化性能。

本结果只支持以上数据生成条件下的比较。{'一次采样不足以判断稳定性，因此同一实验继续补测。' if count == 1 else '20 次采样用于展示波动，尚未进行统计显著性检验。'}
采样数、异常观测和方法改变的是不同条件，不能跨实验直接把数值大小当作方法总排名。

[逐次测量数据](measurements.csv) · [实际配方版本、参数与执行时间](execution.json)

执行记录保存了实际 Git 版本和完整有效配置。查看历史配方时使用该记录的版本，不能以当前配置替代。
""")
    return means


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--materials-script", required=True, type=Path)
    args = parser.parse_args()
    dest = args.output.absolute()
    if dest.exists():
        raise SystemExit("Refusing to overwrite an existing example; review its Git state first")
    dest.mkdir(parents=True)
    parent = dest / "本地主项目"
    workspace = dest / "执行工作区"
    child = workspace / "子项目" / "线性估计对照"
    parent.mkdir(); child.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("materials", args.materials_script)
    materials = importlib.util.module_from_spec(spec); spec.loader.exec_module(materials)
    details = []
    for slug, title, question in [
        ("sample-count", "增加观测数量能否减小参数估计误差", "在方法和噪声水平相同时，增加观测数量是否使估计更准确、更稳定？"),
        ("outlier-resistance", "异常观测下更换估计方法是否有效", "当部分观测明显偏离正常范围时，更换估计方法是否能降低预测误差？")]:
        root = child / "experiments" / slug
        init_git(root)
        write(root / ".gitignore", "models/\n.build/\n__pycache__/\n")
        write(root / "run.py", RUNNER)
        sample = slug == "sample-count"
        baseline = {"name": "Baseline", "n": 8 if sample else 32, "method": "least-squares", "seeds": [7] if sample else list(range(20)), "noise_std": .3, "outlier_shift": 0 if sample else 4}
        variant = {**baseline, "name": "Variant", "n": 32, "method": "least-squares" if sample else "median"}
        for name, value in [("baseline", baseline), ("variant", variant)]:
            json_file(root / "recipes" / (name + ".json"), value)
        write(root / "AGENTS.md", "# 实验入口\n\n先读 EXPERIMENT.md。配置在 recipes/，用 run.py show 查看有效参数，用 measure 执行明确选择。\n共享环境与资源见 ../../../../WORKSPACE.md。材料选择与阶段状态见 records/。\n结果变化时更新所属子项目及本地主项目入口。模型与制作临时文件不进入 Git。\n")
        first = commit(root, "Record reproducible synthetic recipe and launcher")
        common = "真值 y=2x+1；观测噪声标准差 0.3；同一测试网格和配对种子"
        diff = ["8 个观测；最小二乘", "32 个观测；最小二乘"] if sample else ["32 个观测；每 8 个点有 1 个加 4；最小二乘", "相同观测；两两斜率中位数，截距取残差中位数"]
        if sample:
            run_measure(root, "initial")
            plot_and_summarize(root, "initial", title + "：初次测量", common, diff)
            for name, value in [("baseline", baseline), ("variant", variant)]:
                value["seeds"] = list(range(20)); json_file(root / "recipes" / (name + ".json"), value)
            second = commit(root, "Preserve initial evidence and add repeated measurements to recipes")
        else:
            second = first
        run_measure(root, "current")
        means = plot_and_summarize(root, "current", title, common, diff)
        write(root / "CHANGELOG.md", "# 实验变更\n\n" + (
            "1. 首次用一个种子检查观测数量差异，得到可解释结果，保留初测。\n2. 同一问题补充 20 个种子，配方增加测量范围；没有新建实验，也没有把初测覆盖为新结果。\n" if sample else
            "1. 在异常观测这一独立问题下，比较两种估计方法，形成首个结果组。\n") + "\n当前阶段仅检查合成数据中的差异，不证明真实任务收益。核心实验尚未由人选择。\n")
        write(root / "EXPERIMENT.md", f"""# {title}

{question}

当前阶段：本次合成测量已完成，结果与材料记录已保存。展示待人工评阅。

| 结果与用途 | 条件和结果 | 配方与时间 |
|---|---|---|
| [当前结果](results/current/RESULTS.md)：观察{'采样数的影响' if sample else '异常观测下的方法差异'} | 基准 MAE {means[0]:.4f}；对照 {means[1]:.4f}；共同条件和差异在结果表同处展示 | [实际执行记录](results/current/execution.json) |
""" + ("| [初次测量](results/initial/RESULTS.md)：确认输出能解释问题 | 仅一个种子，不能判断稳定性 | [当时配方与时间](results/initial/execution.json) |\n" if sample else "") + """
当前可编辑配方：[基准](recipes/baseline.json) · [对照](recipes/variant.json)。
运行入口：[run.py](run.py)。先用 `show` 查看参数，明确选择后再 `measure`；已有结果目录拒绝覆盖。

复现范围：可从合成数据定义重新生成观测、拟合和测量。依赖 Python 标准库与记录中的实验仓库版本。
图由示例展示工具生成；逐次测量不依赖绘图环境。

[变更记录](CHANGELOG.md) · [材料选择](records/materials.md) · [阶段记录](records/phase.md)
""")
        files = []
        for p in sorted((root / "results").rglob("*")):
            if p.is_file():
                files.append({"path": p.relative_to(root).as_posix(), "kind": "result" if p.suffix != ".json" else "record", "use": "解释条件与结果，复核逐次测量", "keep": "retain", "return": True})
        files.append({"path": "models/last-fit.bin", "kind": "model", "use": "保留最后一次拟合的参数；不作为本地分析交付", "keep": "retain", "return": False})
        files.append({"path": ".build/plot-coordinates.tmp", "kind": "temporary", "use": "绘图前的可再生坐标缓存，当前阶段已无用途", "keep": "cleanup", "return": False})
        policy = {"schema_version": 1, "files": files}
        json_file(root / "records" / "selection.json", policy)
        plan = materials.make_plan(root, policy)
        json_file(root / "records" / "material-plan.json", plan)
        phase = {"scope": "synthetic_current_measurement", "archive": "recorded", "cleanup": "pending", "return": "pending", "human_assessment": "pending", "created_at": datetime.now(UTC).isoformat(), "recipe_commits": [first, second], "items": []}
        json_file(root / "records" / "phase.json", phase)
        local = parent / "experiments" / "线性估计对照" / slug
        materials.verify(root, plan)
        total = sum(o["size"] for o in plan["observed"])
        returned = 0; cleared = 0
        for item, observed in zip(files, plan["observed"]):
            source = root / item["path"]
            if item["return"]:
                target = local / item["path"]; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                assert hashlib.sha256(target.read_bytes()).hexdigest() == observed["sha256"]
                returned += observed["size"]
            if item["keep"] == "cleanup":
                assert hashlib.sha256(source.read_bytes()).hexdigest() == observed["sha256"]
                source.unlink(); cleared += observed["size"]
                phase["items"].append({"path": item["path"], "state": "removed", "sha256": observed["sha256"]})
                json_file(root / "records" / "phase.json", phase)
        phase.update(cleanup="complete", **{"return": "complete"})
        json_file(root / "records" / "phase.json", phase)
        json_file(local / "receipt.json", {"synthetic_local_transfer": True, "received_at": datetime.now(UTC).isoformat(), "files": [o for i,o in zip(files,plan["observed"]) if i["return"]], "model_returned": False})
        write(root / "records" / "materials.md", f"""# 本阶段材料

| 材料 | 用途 | 保留与位置 | 本地接收 |
|---|---|---|---|
| 测量表、结果正文、图及实际配方记录 | 比较条件与结果、独立复核 | 当前结果和仍可信初测保留 | 已接收并逐文件核对，{returned:,} 字节 |
| 拟合参数模型 | 再评估或核查参数 | 模拟远端保留，16 字节 | 不回传 |
| 绘图坐标缓存 | 可由配方重新生成，已无用途 | 阶段记录保存后清理，{cleared:,} 字节 | 不回传 |

明确列出的材料共 {total:,} 字节；这不是整个工作区占用。
代码、配置与轻量记录由实验 Git 保存，未复制完整历史结果树。
详细选择见 [selection.json](selection.json)，清理前预览见 [material-plan.json](material-plan.json)。
预览保留清理前事实，清理后的当前状态以 [phase.json](phase.json) 为准；不能拿旧预览继续删文件。
""")
        write(root / "records" / "phase.md", """# 当前阶段存档

本次合成测量已完成。保留配方、可信测量、结果解释和拟合参数；图前缓存不再使用。

| 事项 | 当前状态 |
|---|---|
| 阶段记录 | 已在清理前保存 |
| 材料清理 | 仅本次生成且校验未变的临时坐标缓存已清理 |
| 结果回传 | 选定可分析材料已复制到模拟本地主项目并核对 |
| 后续工作 | 仍可追加测量，之后可再次阶段存档 |
| 人工评阅／核心实验 | 待评阅；尚未选择核心实验 |

[逐项操作事实](phase.json) · [材料用途与范围](materials.md)
""")
        commit(root, "Record selected result return and phase cleanup without payload copies")
        write(local / "结果.md", f"# {title}\n\n{question}\n\n[当前结果、条件和图](results/current/RESULTS.md)\n\n" + ("[初次测量](results/initial/RESULTS.md)：仍可信，作为补测前的范围对照。\n\n" if sample else "") + "所选数据和执行记录已在本地，不需要从远端路径猜测结果；模型与绘图缓存不在本地包中。\n\n[接收核对记录](receipt.json)\n")
        details.append((slug, title, means, returned, cleared))
    rows = "\n".join(f"| [{title}](experiments/线性估计对照/{slug}/结果.md) | {'固定方法比较 8/32 个观测' if slug == 'sample-count' else '同一异常观测比较两种估计方式'}；当前平均 MAE {v[0]:.4f} / {v[1]:.4f}；[完整条件和依据](experiments/线性估计对照/{slug}/results/current/RESULTS.md) | 本次测量阶段已存档；展示待评阅 | 本地证据 {size:,} 字节；模型留模拟远端；已清理缓存 {clean:,} 字节；[材料与用途](../执行工作区/子项目/线性估计对照/experiments/{slug}/records/materials.md) · [阶段记录](../执行工作区/子项目/线性估计对照/experiments/{slug}/records/phase.md) |" for slug,title,v,size,clean in details)
    write(parent / "EXPERIMENTS.md", "# 实验总览\n\n为什么安排这些实验：先看观测数量的作用，再看异常观测是否改变方法选择。两个问题分别登记；补测属于原实验。\n\n| 实验与目的 | 条件和结果 | 阶段 | 材料状态 |\n|---|---|---|---|\n"+rows+"\n\n核心实验尚未由人选择。选为核心只改变入口的突出展示，不搬动数据。\n")
    write(parent / "experiments" / "线性估计对照" / "结果.md", "# 线性估计对照：子项目结果\n\n这一组实验帮助区分“增加观测”和“更换方法”分别解决什么问题。\n\n"+"\n".join(f"- [{title}]({slug}/结果.md)：{'检查数据量影响' if slug == 'sample-count' else '检查异常观测下的方法选择'}。" for slug,title,_,_,_ in details)+"\n")
    write(parent / "PROJECT.md", """# 线性估计研究：实验管理示例

用两个合成实验检查未来的实验组织方式。这里模拟本地研究管理与远端执行，所有文件都在 test Vault，没有连接服务器。

[实验总览](EXPERIMENTS.md) · [子项目结果](experiments/线性估计对照/结果.md) · [工作区说明](../执行工作区/WORKSPACE.md)

## 当前情况

两项合成实验已产生可分析结果；第一项完成初测和补测，第二项验证不同问题。
结果、图和测量表已选择性接收到此项目，模型留在模拟执行工作区。呈现与操作设计待人工评阅。

## 项目计划

本节是唯一详细计划：先评阅实验总览和两项结果，确认内容足以理解条件、判断结果和决定保留范围；
认可后再将这套规则用于未来新项目。旧档案迁移、真实服务器和发布安装均另行安排。

## 实验与结果

[线性估计对照结果](experiments/线性估计对照/结果.md)：用于区分数据量变化与方法变化，避免将补测当作新实验。
[完整实验表](EXPERIMENTS.md)把共同条件、差异、数值和材料状态放在一起。

尚未选择核心实验。你可以直接指出需要在此突出展示的实验及原因。

## 代码与数据流

```mermaid
flowchart LR
    observations["合成带噪观测"] --> fit["配方指定的拟合方法"]
    fit --> measure["同一测试网格测量"]
    measure --> evidence["结果、图和测量表"]
```

代码只在模拟执行侧维护：[观测数量实验](../执行工作区/子项目/线性估计对照/experiments/sample-count/run.py)、
[异常观测实验](../执行工作区/子项目/线性估计对照/experiments/outlier-resistance/run.py)。
每个实验有独立 Git，多配方共用其仓库。本地结果包不包含代码工作副本。

## 文献与资料

本例未选择论文，不生成新的知识单元。[研究说明](docs/研究说明.md)解释实验问题和指标；
真实项目在这里保留其文献分工、知识笔记和相关原始材料入口。

## 归属与待确认

本地负责计划、知识和跨实验分析；执行侧负责代码、配方、运行事实与重资产。
测试环境中的侧间复制只说明材料边界，不代表已验证 SSH。Git记录不等于外部备份。
本次结果、清理及逐级入口已整理；界面可读性和设计是否实用仍由人评阅。
""")
    write(parent / "docs" / "研究说明.md", "# 两项实验的分工\n\n观测数量实验保持方法不变，考察增加观测是否降低噪声影响。异常观测实验固定观测，考察估计方法是否更稳健。\n\n预测 MAE 将拟合值与已知无噪声真值比较；它与训练点残差不是同一指标。这里选择前者是因为我们关心恢复真实关系的能力。\n")
    write(parent / "AGENTS.md", "# 项目入口\n\n读 PROJECT.md 了解状态和唯一计划，EXPERIMENTS.md 查看实验。共享资源见 ../执行工作区/WORKSPACE.md。\n结果补测或修正后，从实验记录逐级更新子项目结果入口、实验总览和 PROJECT.md；不改变无关知识资料。\n推荐任务需要时再初始化，不生成空任务。用户选择核心实验，禁止按文件大小代替保留用途判断。\n")
    write(parent / ".gitignore", ".DS_Store\n__pycache__/\n*.bundle\n")
    init_git(parent);commit(parent,"Keep local management, selected evidence and navigation")
    write(workspace / "WORKSPACE.md", """# 执行工作区

这是真实服务器的本地合成替身。它是部署和共享资源范围，不是研究层级中的另一个主项目。

| 共享项 | 已有位置或入口 | 特征与用途 | 当前使用者 |
|---|---|---|---|
| Python 环境 | 运行示例时使用的 Python；确切版本在每个 execution.json | 实验仅使用标准库 | 两个线性估计实验 |
| 数据定义 | 各实验配方中的同一 y=2x+1 规则和种子 | 可生成带噪观测，不保存重复的大型数据副本 | 两个实验 |
| 模型 | 各实验 models/last-fit.bin | 每份 16 字节的拟合参数示例，留在执行侧 | 所属实验 |

[线性估计对照子项目](子项目/线性估计对照/PROJECT.md)归属[本地主项目](../本地主项目/PROJECT.md)。
共享环境或资源变化由修改它的 agent 更新这里；配方记录实际使用的版本。
工作区阶段存档引用选定下层阶段记录，检查共享使用者后才清理，没有独立“主管项目”。
""")
    write(child / "PROJECT.md", "# 线性估计对照\n\n这个子项目是一组有关估计条件的实验和工作上下文。\n\n"+"\n".join(f"- [{title}](experiments/{slug}/EXPERIMENT.md)：{'数据量问题' if slug == 'sample-count' else '异常观测问题'}。" for slug,title,_,_,_ in details)+"\n\n[本地主项目](../../../本地主项目/PROJECT.md) · [共享资源](../../WORKSPACE.md)\n\n当前两项测量阶段已经整理；未来补测仍在各自实验中登记。\n")
    write(child / "AGENTS.md", "# 子项目规则\n\n研究归属见 PROJECT.md，环境与资源见 ../../WORKSPACE.md。每个实验保留独立仓库，子项目Git不追踪其内部。\n实验工作完成后，负责的同一agent更新本子项目及本地主项目入口；不要在此建立第二个总体计划。\n")
    write(child / ".gitignore", "experiments/\n")
    init_git(child);commit(child,"Keep group context without tracking nested experiment repositories")
    write(dest / ".gitignore", "本地主项目/\n执行工作区/子项目/\n_work/\n")
    write(dest / "README.md", """# 未来实验管理样例

从[本地主项目](本地主项目/PROJECT.md)或[实验总览](本地主项目/EXPERIMENTS.md)开始。

这是一个新样例；没有调整旧档案。两项合成实验实际计算，用于检查文件关系与可读呈现，不代表真实科研结论或已安装插件验收。

先看条件和结果能否同时读懂，再看[工作区](执行工作区/WORKSPACE.md)与各实验的材料／阶段记录。
第一项实验保留初测和补测，第二项对应独立问题。模型不回传；只清理本例生成的图前临时坐标缓存。

本地主项目、子项目上下文和两个实验各有独立 Git；上级不递归跟踪嵌套仓库，不推送。
所有配置、记录和结果均可直接编辑，代码在模拟执行侧。呈现待人工评阅。
""")
    print(json.dumps({"entry": str(parent / "PROJECT.md"), "experiments": len(details), "synthetic": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
