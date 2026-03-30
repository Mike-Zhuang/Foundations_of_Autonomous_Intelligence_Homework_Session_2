# YOLO 人车交通识别 — 技术操作说明

**原始 PDF**：project/YOLO人车交通识别操作说明.pdf

## 目录

- [概览](#概览)
- [关键要点速览](#关键要点速览)
- [拍摄要求与点位选择](#拍摄要求与点位选择)
- [环境与依赖安装（示例）](#环境与依赖安装示例)
- [运行脚本（示例）](#运行脚本示例)
- [逆透视矫正（标定）](#逆透视矫正标定)
- [数据导出格式](#数据导出格式)
- [自定义人流统计](#自定义人流统计)
- [流向统计示例](#流向统计示例)
- [兜底方案与人工校验](#兜底方案与人工校验)

---

## 概览

本说明基于原始 PPT/PDF，整理为面向工程的操作文档，保留原始要点与示意图，去除临时提取脚本和冗余调试信息以便直接用于部署与运行。

---

## 关键要点速览

- 使用 YOLO 框架对人、车、自行车等目标进行检测与跟踪；通过逆透视标定将像素运动转换为实际速度。
- 拍摄时需保证地面标注矩形（用于标定）、视野覆盖目标入口/出口、环境光线充足且画面稳定。
- 建议用 Anaconda 管理 Python 环境（示例使用 Python 3.12）。

---

## 拍摄要求与点位选择

- 地面须标注一个有尺寸的矩形（用于逆透视和速度计算）。
- 优先高处俯拍以减少遮挡，确保能完整看到人/车与其接地点（bounding box 底部中心接近人的脚）。
- 环境光线充足且摄像机稳定，视野尽量覆盖全部出入口。

示意图（示例）：

![拍摄示意](../doc_images/YOLO_manual_images/image_page_2_2.png)

---

## 环境与依赖安装（示例）

以下为 PPT 中给出的安装步骤与注释（已保留原注释，按需粘贴到命令行/脚本中执行）：

```bash
# 1. 设定清华源 (如果之前设过可以跳过)
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
conda config --set show_channel_urls yes
# 2. 创建 Python 3.12 环境
conda create -n traffic_cpu python=3.12 -y
# 3. 激活环境
conda activate traffic_cpu
# 设定 pip 清华源加速
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
# 安装核心库 (会自动安装轻量版 Torch 和所有依赖)
pip install ultralytics deep-sort-realtime pandas openpyxl pillow opencv-python
```

说明：上述为示例命令，实际环境名称与版本请根据你的系统与需求调整（例如可用已有 `yolo` 环境替代 `traffic_cpu`）。

示意：

![依赖安装示意](../doc_images/YOLO_manual_images/image_page_4_2.png)

---

## 运行脚本（示例）

项目中常见脚本：

- `yolo_process.py`：处理视频/图片，执行检测、跟踪并导出结果（按提示输入路径与文件夹名）。
- `yolo_read.py`：对导出结果进行交互式可视化统计，点选出入口区域生成汇总表格。

命令示例：

```bash
python path/to/yolo_process.py
python path/to/yolo_read.py
```

（具体脚本参数按项目中脚本头部的使用说明执行。）

示意图：

![脚本调用示意](../doc_images/YOLO_manual_images/image_page_5_2.png)

---

## 逆透视矫正（标定）

操作要点：

- 依次点击预设矩形四个角（左上、右上、右下、左下）。
- 输入矩形的宽（左上到右上）和高（左上到左下），作为物理尺度参考。 
- 绘制地面区域，点选后按 `C` 键闭合以完成标定。

示意图：

![逆透视：输入尺寸](../doc_images/YOLO_manual_images/image_page_6_2.png)
![逆透视：绘制地面并闭合](../doc_images/YOLO_manual_images/image_page_7_2.png)

---

## 数据导出格式

导出数据包含每个跟踪对象的基本字段：`ID`、`Type`、`平均速度 (m/s)` 等。示例（节选）：

```
ID
Type
平均速度
(m/s)
1
Person
2.432
14
Person
1.943
...
```

示意图：

![导出数据示意](../doc_images/YOLO_manual_images/image_page_8_2.png)

---

## 自定义人流统计

使用 `yolo_read.py` 填入结果目录后，可交互式点选出入口区域，程序会统计经过各入口的对象类型并输出表格/可视化图表，便于后续分析。

示例：

![人流统计示例 A](../doc_images/YOLO_manual_images/image_page_9_2.png)
![人流统计示例 B](../doc_images/YOLO_manual_images/image_page_9_3.png)
![人流统计示例 C](../doc_images/YOLO_manual_images/image_page_9_4.png)

---

## 流向统计示例

示例表格（节选）：

```
流向  快走的人  慢走的人  骑自行车  汽车
A→B   0        0         0       0
A→C   1        0         0       0
...（完整示例见项目数据）
```

示意图：

![流向统计示意](../doc_images/YOLO_manual_images/image_page_10_2.png)

---

## 兜底方案与人工校验

建议：每个出入口安排人工计数并录像用于验证与估速；可让一位同学匀速走作为对比样本，便于评估速度判定阈值。

示意图：

![兜底方案示意](../doc_images/YOLO_manual_images/image_page_11_2.png)


