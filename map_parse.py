# 下载地图瓦片并拼接大图，裁剪并计算坐标偏移

import os
import json
import time
import requests
from PIL import Image
from collections import defaultdict

Image.MAX_IMAGE_PIXELS = None

# ======================== 常量 ========================

TILE_API_URL = "https://api.kurobbs.com/map/core/config/getMapIdList"
RESOURCE_API_URL = "https://api.kurobbs.com/map/core/config/getMapResource"
BASE_URL_TEMPLATE = "https://web-static.kurobbs.com/mcmap/tiles/{resource_id}/{key}/"

TILE_SIZE = 1024  # 单张瓦片的像素尺寸
GAME_SCALE = 83.008  # 像素到游戏坐标的缩放系数
LEAFLET_W = 1024  # Leaflet 瓦片宽度偏移量

DOWNLOAD_DIR = "orig_map"
OUTPUT_DIR = "output"


# ======================== API 请求 ========================

def fetch_resource_id() -> str:
    """从 getMapResource 接口获取资源 ID，用于拼接瓦片下载地址"""
    resp = requests.post(RESOURCE_API_URL, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 200:
        raise RuntimeError(f"获取资源 ID 失败: {result}")
    return result["data"]


def fetch_tile_map() -> dict:
    """从 getMapIdList 接口获取瓦片映射表 {key: [tile_id, ...]}"""
    resp = requests.post(TILE_API_URL, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 200:
        raise RuntimeError(f"获取瓦片列表失败: {result}")
    return result["data"]


# ======================== 瓦片下载 ========================

def parse_tile_id(tile_id: str) -> tuple:
    """
    解析瓦片标识字符串，格式："{图片编号}_{x}_{y}"
    例如 "8_-1_-1" -> (8, -1, -1)
    """
    parts = tile_id.split('_')
    if len(parts) != 3:
        raise ValueError(f"无效的瓦片标识: {tile_id}，应为 编号_x_y")
    return int(parts[0]), int(parts[1]), int(parts[2])


def download_tile_if_not_exists(tile_id: str, base_url: str, download_dir: str) -> str:
    """若本地不存在则下载瓦片，返回本地文件路径"""
    save_path = os.path.join(download_dir, f"{tile_id}.png")
    if os.path.exists(save_path):
        print(f"文件已存在，跳过下载: {save_path}")
        return save_path

    url = base_url + tile_id + ".png"
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            print(f"下载成功: {url} -> {save_path}")
            return save_path
        except Exception as e:
            print(f"下载失败 (第{attempt}次): {url}, 错误: {e}")
            if attempt < 3:
                time.sleep(5)
    raise RuntimeError(f"下载失败，已重试3次: {url}")


# ======================== 图片拼接与裁剪 ========================

def stitch_group(images: list) -> tuple:
    """
    将同一组的瓦片按坐标拼接到一张大图上
    返回 (canvas, min_x, min_y)，若 images 为空则返回 (None, None, None)
    """
    if not images:
        return None, None, None

    tiles = []
    xs, ys = [], []
    for x, y, path in images:
        img = Image.open(path).convert('RGBA')
        tiles.append((x, y, img))
        xs.append(x)
        ys.append(y)

    # 校验所有瓦片尺寸一致
    tile_w, tile_h = tiles[0][2].size
    for _, _, img in tiles:
        if img.size != (tile_w, tile_h):
            raise ValueError(f"图片尺寸不一致: {img.size} vs ({tile_w}, {tile_h})")

    # 计算画布尺寸并粘贴各瓦片
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = (max_x - min_x + 1) * tile_w
    height = (max_y - min_y + 1) * tile_h
    canvas = Image.new('RGBA', (width, height), (255, 255, 255, 0))

    for x, y, img in tiles:
        paste_x = (x - min_x) * tile_w
        paste_y = (y - min_y) * tile_h
        canvas.paste(img, (paste_x, paste_y), img)

    return canvas, min_x, min_y


def is_blank_pixel(pixel: tuple) -> bool:
    """判断像素是否为空白（透明 / 纯黑 / 纯白）"""
    r, g, b, a = pixel
    return a == 0 or (r, g, b) in ((0, 0, 0), (255, 255, 255))


def trim_edges(img: Image.Image) -> tuple:
    """
    裁剪图片四周的空白区域
    返回 (裁剪后图片, 左侧裁切像素数, 顶部裁切像素数)
    """
    px = img.load()
    w, h = img.size

    top = 0
    while top < h and all(is_blank_pixel(px[x, top]) for x in range(w)):
        top += 1

    bottom = h - 1
    while bottom >= top and all(is_blank_pixel(px[x, bottom]) for x in range(w)):
        bottom -= 1

    left = 0
    while left < w and all(is_blank_pixel(px[left, y]) for y in range(h)):
        left += 1

    right = w - 1
    while right >= left and all(is_blank_pixel(px[right, y]) for y in range(h)):
        right -= 1

    if top > bottom or left > right:
        return img, 0, 0
    return img.crop((left, top, right + 1, bottom + 1)), left, top


# ======================== 坐标计算 ========================

def compute_coord_ref(min_orig_x: int, min_adj_y: int,
                      crop_left: int, crop_top: int,
                      img_width: int, img_height: int) -> dict:
    """
    根据拼接与裁剪参数计算游戏坐标参考信息
    返回包含 offset / scale / center / min / max 的字典
    """
    offset_x = (crop_left + min_orig_x * TILE_SIZE - LEAFLET_W) * GAME_SCALE
    offset_y = (crop_top + min_adj_y * TILE_SIZE) * GAME_SCALE

    center_game_x = (img_width / 2.0) * GAME_SCALE + offset_x
    center_game_y = (img_height / 2.0) * GAME_SCALE + offset_y

    return {
        "offset": [offset_x, offset_y],
        "scale": [GAME_SCALE, GAME_SCALE],
        "center": [center_game_x, center_game_y],
        "min": [offset_x, offset_y],
        "max": [img_width * GAME_SCALE + offset_x, img_height * GAME_SCALE + offset_y]
    }


# ======================== 主流程 ========================

def process_map_group(key: str, tile_ids: list, base_url: str, download_dir: str, output_dir: str):
    """处理单个地图分组：下载瓦片 -> 拼接 -> 裁边 -> 保存坐标，返回坐标参考信息"""
    groups = defaultdict(list)

    for tile_id in tile_ids:
        img_id, orig_x, orig_y = parse_tile_id(tile_id)
        adjusted_y = -orig_y  # Y 轴方向翻转：瓦片坐标与图片坐标 Y 方向相反
        file_path = download_tile_if_not_exists(tile_id, base_url, download_dir)
        groups[img_id].append((orig_x, adjusted_y, file_path))

    coord_ref = None
    for img_id, tile_list in groups.items():
        tile_list.sort(key=lambda item: (item[0], item[1]))
        canvas, min_orig_x, min_adj_y = stitch_group(tile_list)
        if canvas is None:
            continue

        orig_path = os.path.join(output_dir + "/orig", f"{key}.png")
        canvas.save(orig_path, 'PNG')
        print(f"已保存原始拼接图片: {orig_path}")

        trimmed, crop_left, crop_top = trim_edges(canvas)
        trimmed_path = os.path.join(output_dir + "/trimmed", f"{key}.png")
        trimmed.save(trimmed_path, 'PNG')
        print(f"已保存裁边图片: {trimmed_path}")

        coord_ref = compute_coord_ref(
            min_orig_x, min_adj_y, crop_left, crop_top,
            trimmed.size[0], trimmed.size[1]
        )
    return coord_ref


def main():
    # 动态获取资源 ID，用于拼接瓦片下载地址
    resource_id = fetch_resource_id()
    print(f"获取到资源 ID: {resource_id}")

    tile_map = fetch_tile_map()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR + '/orig', exist_ok=True)
    os.makedirs(OUTPUT_DIR + '/trimmed', exist_ok=True)

    all_map_coords = {}
    for key, tile_ids in tile_map.items():
        base_url = BASE_URL_TEMPLATE.format(resource_id=resource_id, key=key)
        print(f"\n===== 处理地图 key={key}, 瓦片数={len(tile_ids)} =====")
        coord_ref = process_map_group(key, tile_ids, base_url, DOWNLOAD_DIR, OUTPUT_DIR)
        if coord_ref is not None:
            all_map_coords[key] = coord_ref

    coord_path = os.path.join(OUTPUT_DIR, "map_coords.json")
    with open(coord_path, 'w', encoding='utf-8') as f:
        json.dump(all_map_coords, f, indent=2)
    print(f"\n已保存合并坐标文件: {coord_path}")

    print("\n所有拼接完成！")


if __name__ == "__main__":
    main()
