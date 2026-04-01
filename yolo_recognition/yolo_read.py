import os, cv2, json, pandas as pd, numpy as np
from PIL import Image, ImageDraw, ImageFont

# --- 全局交互变量 ---
zones, current_pts = [], []

def draw_chinese_text(img, text, position, color=(255, 255, 255), size=20):
    """ 在图像上绘制高清中文 """
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    # 尝试加载 Windows 标准微软雅黑，若无则使用默认
    font_paths = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"]
    font = ImageFont.load_default()
    for path in font_paths:
        if os.path.exists(path):
            font = ImageFont.truetype(path, int(size))
            break
    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def is_point_in_zone(point, zone_pts):
    """ 判断点是否在多边形内 (修复类型错误) """
    pt = (float(point[0]), float(point[1]))
    contour = np.array(zone_pts, np.int32)
    return cv2.pointPolygonTest(contour, pt, False) >= 0

def stitch_tracks(df, fps, d_thresh=2.5, t_thresh=3.0):
    """ 轨迹缝合：合并因遮挡而断裂的同一 ID """
    ids = df['ID'].unique()
    if len(ids) == 0: return df
    t_info = {tid: {'f1':df[df['ID']==tid]['Frame'].iloc[-1], 
                    'p1':(df[df['ID']==tid]['RX'].iloc[-1], df[df['ID']==tid]['RY'].iloc[-1]),
                    'f0':df[df['ID']==tid]['Frame'].iloc[0], 
                    'p0':(df[df['ID']==tid]['RX'].iloc[0], df[df['ID']==tid]['RY'].iloc[0]),
                    'type':df[df['ID']==tid]['Type'].iloc[0]} for tid in ids}
    mapping = {tid: tid for tid in ids}
    s_ids = sorted(ids, key=lambda x: t_info[x]['f0'])
    for i in range(len(s_ids)):
        for j in range(i+1, len(s_ids)):
            id1, id2 = s_ids[i], s_ids[j]
            t_gap = (t_info[id2]['f0'] - t_info[id1]['f1']) / fps
            d_gap = np.sqrt((t_info[id2]['p0'][0]-t_info[id1]['p1'][0])**2 + (t_info[id2]['p0'][1]-t_info[id1]['p1'][1])**2)
            if 0 < t_gap < t_thresh and d_gap < d_thresh and t_info[id1]['type'] == t_info[id2]['type']:
                mapping[id2] = mapping[id1]
                t_info[id1]['f1'], t_info[id1]['p1'] = t_info[id2]['f1'], t_info[id2]['p1']
    df['ID'] = df['ID'].map(mapping)
    return df

def mouse_event(event, x, y, flags, param):
    global current_pts
    if event == cv2.EVENT_LBUTTONDOWN:
        current_pts.append((x, y))

def run_od_analyzer():
    global current_pts, zones
    proj_dir = input("\n请输入项目路径: ").strip().strip('"')
    if not os.path.exists(proj_dir):
        print("错误：找不到项目目录！"); return

    bg = cv2.imread(os.path.join(proj_dir, "background.jpg"))
    df = pd.read_csv(os.path.join(proj_dir, "tracks.csv"))
    with open(os.path.join(proj_dir, "config.json"), "r") as f:
        conf = json.load(f)

    print("\n[1/3] 执行轨迹缝合与清洗...")
    df = stitch_tracks(df, conf['fps'])
    
    # --- 【核心修改：预渲染边界与流线背景图】 ---
    print("[2/3] 正在生成流线与边界可视化背景，请稍候...")
    viz_bg = bg.copy()
    
    # 1. 绘制地面边界 ROI (灰色连线)
    if "boundary" in conf and len(conf["boundary"]) > 1:
        boundary_poly = np.array(conf["boundary"], np.int32)
        cv2.polylines(viz_bg, [boundary_poly], True, (120, 120, 120), 2)
        # 添加半透明填充
        mask = viz_bg.copy()
        cv2.fillPoly(mask, [boundary_poly], (80, 80, 80))
        cv2.addWeighted(mask, 0.3, viz_bg, 0.7, 0, viz_bg)
    
    # 2. 绘制各物体流线 (彩色)
    # 按ID分组获取所有轨迹点
    for tid, g in df.groupby("ID"):
        t_id = g["Type"].iloc[0]
        # 获取像素轨迹点序列
        path_points = g[['PX_X', 'PX_Y']].values.astype(int)
        
        if len(path_points) > 1:
            # 颜色同步：行人黄色，自行车紫色，汽车青色
            color = {0:(0,255,255), 1:(255,0,255), 2:(255,255,0)}.get(t_id, (0,255,0))
            # 绘制流线，粗细为 1 (不干扰画面)
            cv2.polylines(viz_bg, [path_points], False, color, 1)
            
            # 绘制起点(绿)和终点(红)
            cv2.circle(viz_bg, tuple(path_points[0]), 3, (0, 255, 0), -1)
            cv2.circle(viz_bg, tuple(path_points[-1]), 3, (0, 0, 255), -1)

    print("[3/3] 预渲染完成。现在开始划定交通分区。")
    # --- 【预渲染结束】 ---

    cv2.namedWindow("OD_Zone_Drawer", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("OD_Zone_Drawer", mouse_event)
    
    print("\n[交互引导] A/B/C 节点绘制：")
    print(" - 点击【左键】落点绘制多边形断面")
    print(" - 按 【C】 闭合当前多边形并存为 A/B/C 区")
    print(" - 按 【R】 重置当前正在画的线")
    print(" - 按 【S】 保存并执行流向分析")

    while True:
        # 使用预渲染了流线和边界的 viz_bg
        canvas = viz_bg.copy()
        
        # 绘制已确定的 OD 断面分区
        for z in zones:
            pts_arr = np.array(z["points"], np.int32)
            cv2.polylines(canvas, [pts_arr], True, (0, 165, 255), 3) # 橙色断面
            canvas = draw_chinese_text(canvas, f"节点 {z['name']}", z["points"][0], (255, 255, 0), 30)
        
        # 绘制正在画的分区
        if len(current_pts) > 0:
            for p in current_pts: cv2.circle(canvas, p, 5, (0, 0, 255), -1)
            if len(current_pts) > 1:
                cv2.polylines(canvas, [np.array(current_pts, np.int32)], False, (0, 255, 255), 2)

        cv2.imshow("OD_Zone_Drawer", canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('c') or key == ord('C'):
            if len(current_pts) >= 3:
                z_name = chr(65 + len(zones)) # A, B, C...
                zones.append({"name": z_name, "points": current_pts.copy()})
                current_pts = []
                print(f"已锁定节点 {z_name}")
        elif key == ord('r') or key == ord('R'):
            current_pts = []
        elif key == ord('s') or key == ord('S'):
            if len(zones) < 2:
                print("警告：请至少划定两个分区进行 OD 分析！")
            else:
                break
        elif key == 27: # ESC
            return

    cv2.destroyAllWindows()
    print("\n最后计算矩阵中...")

    # 提取所有 ID 的流向特征
    id_beh = {}
    for tid, g in df.groupby("ID"):
        t_id = g["Type"].iloc[0]
        pts_r = g[["RX", "RY"]].values
        dist = np.sum(np.sqrt(np.sum(np.diff(pts_r, axis=0)**2, axis=1)))
        dur = len(g) / conf["fps"]; avg_v = dist / dur if dur > 0 else 0
        t_name = "未知"
        if t_id == 0: t_name = "快走的人" if avg_v >= 1.4 else "慢走的人"
        elif t_id == 1: t_name = "骑自行车"
        elif t_id == 2: t_name = "汽车"
        id_beh[tid] = {"start_px": (g["PX_X"].iloc[0], g["PX_Y"].iloc[0]), "end_px": (g["PX_X"].iloc[-1], g["PX_Y"].iloc[-1]), "type": t_name}

    # 填充矩阵
    results = []
    for z_o in zones:
        for z_d in zones:
            if z_o == z_d: continue
            direction = f"{z_o['name']} → {z_d['name']}"
            counts = {"快走的人": 0, "慢走的人": 0, "骑自行车": 0, "汽车": 0}
            for tid, info in id_beh.items():
                if is_point_in_zone(info["start_px"], z_o["points"]) and \
                   is_point_in_zone(info["end_px"], z_d["points"]):
                    if info["type"] in counts: counts[info["type"]] += 1
            results.append({"流向": direction, **counts})

    # 输出报表
    od_df = pd.DataFrame(results); save_name = os.path.join(proj_dir, "OD_Trajectory_Report.xlsx")
    od_df.to_excel(save_name, index=False)
    print("\n" + "="*30 + "\n" + od_df.to_string(index=False) + "\n" + "="*30)
    print(f"OD 轨迹流向报表已保存：\n{save_name}")

if __name__ == "__main__":
    run_od_analyzer()