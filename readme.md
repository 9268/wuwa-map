# Kuro Map Data Collection

基于库洛官方「库街区」大地图 API 采集并处理的游戏地图数据与可采集品数据集，并提供地图特征提取与截图匹配工具。

## 📖 项目介绍

本项目使用库街区大地图（[https://www.kurobbs.com/mc/map/](https://www.kurobbs.com/mc/map/)）的公开 API，对地图数据进行自动化采集与预处理。目前包含以下数据资源：

1. **地图瓦片与拼合图像**  
   - 原始地图瓦片（XYZ 切片）  
   - 已拼接好的各区域完整地图  
   - 裁剪无效区域后的精简拼接地图  
   - 地图坐标 ↔ 游戏坐标的转换说明文件  

2. **可采集品收集**  
   采集各类资源点的类型、坐标与分布信息，经整理后形成结构化数据集。

## 📊 当前数据完成度

共覆盖 **8 个区域**，采集详情如下：

| 区域 | id  | 物品种类     | 采集点位置数 |
|--------------------|-----|----------|--------------|
| 阿维纽林           | 903 | 31 | 453      |
| 下层金库           | 902 | 37  | 238      |
| 黯原              | 909 | 41  | 650      |
| 罗伊冰原           | 906 | 74  | 2,516    |
| 瑝珑、黑海岸群岛、黎那汐塔、罗伊冰原 | 8   | 388 | 17,700   |
| 泰缇斯之底          | 900 | 40  | 415      |
| 隐海试验场          | 905 | 35  | 236      |
| 时隙废都            | 910 | 9   | 59       |

## 🔧 特征提取与匹配工具

提供命令行工具，用于从拼接地图中提取图像特征，并与游戏截图进行匹配，自动定位截图在地图中的位置。

### 1. 特征提取

```bash
python -m match_engine.common extract \
  --dir assets/stitched \          # 拼接地图所在目录
  --out src/match_engine/assets \  # 输出特征文件目录
  --algo surf \                    # 特征算法 (surf 或 orb)
  --grid 100 \                     # 网格大小 (px)
  --max-per-cell 160               # 每个网格最多保留特征点
```
输出：结构化的 JSON 文件，每张图一条记录，包含 file, out, size, total_features, saved_features。

### 2. 截图匹配
```bash
python -m src.match_engine.common match \
  --query path/to/screenshot.png \        # 游戏截图路
  --features src/match_engine/assets/900_surf.npz \  # 预提取的特征文件
  --coords assets/stitched/900_coords.json \        # 地图坐标映射文件
  --algo surf \                           # 需与提取时一致
  --crop 0                                # 裁剪边缘像素 (0 表示不裁剪)
```

输出：结构化 JSON，包含：

- success：是否匹配成功
- match_count / inlier_count：匹配点数量
- confidence：置信度
- elapsed_ms：耗时
- center / corners：匹配中心点和四角坐标
- game_center：对应游戏世界坐标

## ⚠️ 其他说明
### 特征参数文件不在 Release 中提供
由于 GitHub Actions 内存限制，无法自动运行特征提取，因此 Release 仅包含原始数据和采集点信息。请你在本地运行上述 extract 命令自行生成特征文件。

### SURF 算法依赖
使用 --algo surf 需要安装带有 xfeatures2d 扩展的 OpenCV（如 opencv-contrib-python）。若环境不支持 SURF，可使用 --algo orb 作为替代（匹配精度稍低）。
