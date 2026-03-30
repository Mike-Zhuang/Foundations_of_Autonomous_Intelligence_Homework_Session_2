import os, cv2, json, sys, numpy as np, pandas as pd
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from collections import deque
from PIL import Image, ImageDraw, ImageFont

# --- 核心算法配置 ---
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
MATH_ALPHA = 0.15     # 测速平滑权重
VECTOR_EMA = 0.2      # 惯性向量平滑权重
SPEED_WINDOW = 15     # 测速中值滤波窗口
MAX_SPEED_MAP = {0: 25, 1: 65, 2: 180} # 时速上限(km/h)
MAX_JUMP_MAP = {0: 0.8, 1: 1.5, 2: 3.5} # 物理防漂移跳变阈值(米/帧)

pts, boundary_pts, m_pos = [], [], (0, 0)
boundary_closed = False 

def get_iou(box1, box2):
    x1, y1, w1, h1 = box1; x2, y2, w2, h2 = box2
    xi1, yi1, xi2, yi2 = max(x1, x2), max(y1, y2), min(x1+w1, x2+w2), min(y1+h1, y2+h2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0

def draw_ui_text(img, text, position, color=(0, 255, 0), size=25):
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font_path = "C:/Windows/Fonts/msyh.ttc"
    try: font = ImageFont.truetype(font_path, size)
    except: font = ImageFont.load_default()
    draw.text(position, text, font=font, fill=color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

def mouse_handler(event, x, y, flags, param):
    global pts, boundary_pts, m_pos, boundary_closed
    m_pos = (x, y)
    if event == cv2.EVENT_LBUTTONDOWN:
        if param == "calib":
            if len(pts) < 4: pts.append((x, y))
        else:
            if not boundary_closed: boundary_pts.append((x, y))

def get_config(frame):
    global pts, boundary_pts, m_pos, boundary_closed
    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Magnifier", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Magnifier", cv2.WND_PROP_TOPMOST, 1)
    
    cv2.setMouseCallback("Calibration", mouse_handler, "calib")
    while True:
        draw = frame.copy(); mx, my = m_pos
        crop = frame[max(0,my-40):min(frame.shape[0],my+40), max(0,mx-40):min(frame.shape[1],mx+40)]
        if crop.size > 0:
            zoom = cv2.resize(crop, (250, 250), interpolation=cv2.INTER_NEAREST)
            cv2.line(zoom, (0, 125), (250, 125), (255, 255, 255), 1)
            cv2.line(zoom, (125, 0), (125, 250), (255, 255, 255), 1)
            cv2.imshow("Magnifier", zoom)
        for i, p in enumerate(pts):
            cv2.circle(draw, p, 5, (0, 0, 255), -1)
            if i > 0: cv2.line(draw, pts[i-1], pts[i], (0, 255, 0), 2)
            if i == 3: cv2.line(draw, pts[3], pts[0], (0, 255, 0), 2)
        msg = f"步骤1: 点击地面4个角 ({len(pts)}/4)" if len(pts) < 4 else "已选满，按回车确认，R重选"
        draw = draw_ui_text(draw, msg, (20, 30), color=(0,255,255) if len(pts)==4 else (0,255,0))
        cv2.imshow("Calibration", draw)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('r'): pts = []
        elif key == 13 and len(pts) == 4: break

    rw = float(input("物理宽度(m): ")); rh = float(input("物理长度(m): "))
    M = cv2.getPerspectiveTransform(np.array(pts, dtype="float32"), np.array([[0,0],[rw,0],[rw,rh],[0,rh]], dtype="float32"))

    cv2.setMouseCallback("Calibration", mouse_handler, "boundary")
    boundary_closed = False
    while True:
        draw = frame.copy()
        cv2.polylines(draw, [np.array(pts, np.int32)], True, (0, 255, 0), 1)
        if len(boundary_pts) > 0:
            cv2.polylines(draw, [np.array(boundary_pts, np.int32)], boundary_closed, (255, 255, 0), 2)
            if boundary_closed:
                mask = draw.copy(); cv2.fillPoly(mask, [np.array(boundary_pts, np.int32)], (255, 255, 0))
                cv2.addWeighted(mask, 0.4, draw, 0.6, 0, draw)
        msg = f"步骤2: 勾勒地面区 ({len(boundary_pts)}点, C闭合, S开始)" if not boundary_closed else "区域已锁定，按 S 开始"
        draw = draw_ui_text(draw, msg, (20, 30))
        cv2.imshow("Calibration", draw)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('c'): boundary_closed = True
        elif key == ord('r'): boundary_pts = []; boundary_closed = False
        elif key == ord('s') and boundary_closed: break
    cv2.destroyAllWindows()
    return M.tolist(), rw, rh, boundary_pts

def run_processor():
    m_path = input("YOLO权重路径: ").strip().strip('"')
    base_dir = input("项目目录: ").strip().strip('"')
    p_name = input("项目名称: ").strip()
    v_path = input("视频路径: ").strip().strip('"')
    proj_dir = os.path.join(base_dir, p_name); os.makedirs(proj_dir, exist_ok=True)
    
    model = YOLO(m_path); cap = cv2.VideoCapture(v_path)
    fps, total_f = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    v_w, v_h = int(cap.get(3)), int(cap.get(4))
    
    ret, first_frame = cap.read()
    if not ret: return
    M_list, rw, rh, b_pts = get_config(first_frame)
    M, boundary_poly = np.array(M_list), np.array(b_pts, np.int32)
    cv2.imwrite(os.path.join(proj_dir, "background.jpg"), first_frame)

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    video_out = cv2.VideoWriter(os.path.join(proj_dir, "result_video.mp4"), cv2.VideoWriter_fourcc(*'mp4v'), fps, (v_w, v_h))
    tracker = DeepSort(max_age=60, n_init=5)
    math_coords, speed_bufs, last_vectors, detailed_data = {}, {}, {}, []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret: break
        f_idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        cv2.polylines(frame, [boundary_poly], True, (100, 100, 100), 2)
        results = model.predict(frame, conf=0.4, verbose=False, imgsz=640, device='cpu')[0]
        
        raw_p, raw_b, raw_o = [], [], []
        for box in results.boxes:
            b = box.xyxy[0].cpu().numpy()
            cid = int(box.cls[0].cpu().numpy())
            bc = (float((b[0]+b[2])/2), float(b[3]))
            if cv2.pointPolygonTest(boundary_poly, bc, False) >= 0:
                item = [[b[0], b[1], b[2]-b[0], b[3]-b[1]], box.conf[0].cpu().numpy(), cid]
                if cid == 0: raw_p.append(item)
                elif cid == 1: raw_b.append(item)
                else: raw_o.append(item)
        
        keep_p = [p for p in raw_p if not any(get_iou(p[0], b[0]) > 0.25 for b in raw_b)]
        tracks = tracker.update_tracks(raw_b + keep_p + raw_o, frame=frame)
        
        for t in tracks:
            if not t.is_confirmed(): continue
            tid, cid, l, top, r, bottom = t.track_id, int(t.get_det_class()), *t.to_ltrb()
            p_raw = cv2.perspectiveTransform(np.array([[[ (l+r)/2, bottom ]]], dtype="float32"), M)[0][0]
            rx, ry = p_raw[0], p_raw[1]

            if tid in math_coords:
                prev_rx, prev_ry = math_coords[tid]
                if np.sqrt((rx-prev_rx)**2 + (ry-prev_ry)**2) > MAX_JUMP_MAP.get(cid, 2.0):
                    if tid in last_vectors:
                        vx, vy = last_vectors[tid]; rx, ry = prev_rx + vx, prev_ry + vy
                    else: rx, ry = prev_rx, prev_ry
                else:
                    cx, cy = rx-prev_rx, ry-prev_ry
                    if tid not in last_vectors: last_vectors[tid] = (cx, cy)
                    else:
                        lx, ly = last_vectors[tid]
                        last_vectors[tid] = (VECTOR_EMA*cx+0.8*lx, VECTOR_EMA*cy+0.8*ly)

            v_f = 0.0
            if tid not in math_coords:
                math_coords[tid], speed_bufs[tid] = (rx, ry), deque(maxlen=SPEED_WINDOW)
            else:
                old_mx, old_my = math_coords[tid]
                m_sx = MATH_ALPHA * rx + (1 - MATH_ALPHA) * old_mx
                m_sy = MATH_ALPHA * ry + (1 - MATH_ALPHA) * old_my
                dist = np.sqrt((m_sx - old_mx)**2 + (m_sy - old_my)**2)
                if (dist * fps * 3.6) < MAX_SPEED_MAP.get(cid, 120): speed_bufs[tid].append(dist * fps * 3.6)
                if speed_bufs[tid]: v_f = np.median(speed_bufs[tid])
                math_coords[tid] = (m_sx, m_sy)

            color = {0:(0,255,255), 1:(255,0,255), 2:(255,255,0)}.get(cid, (0,255,0))
            cv2.rectangle(frame, (int(l), int(top)), (int(r), int(bottom)), color, 2)
            cv2.putText(frame, f"ID:{tid} {v_f:.1f}kph", (int(l), int(top)-10), 0, 0.6, color, 2)
            detailed_data.append({"Frame": f_idx, "ID": tid, "Type": cid, "RX": round(rx,3), "RY": round(ry,3), "PX_X": int((l+r)/2), "PX_Y": int(bottom)})

        video_out.write(frame)
        if f_idx % 10 == 0: sys.stdout.write(f"\r进度: {f_idx/total_f*100:.1f}%"); sys.stdout.flush()

    # --- 最终导出 (包含 Excel 简表) ---
    df = pd.DataFrame(detailed_data)
    df.to_csv(os.path.join(proj_dir, "tracks.csv"), index=False)
    
    summary = []
    for tid, g in df.groupby("ID"):
        pts_r = g[["RX", "RY"]].values
        # 累计物理距离计算
        dist = np.sum(np.sqrt(np.sum(np.diff(pts_r, axis=0)**2, axis=1)))
        dur = len(g) / fps
        avg_v_kph = (dist / dur) * 3.6 if dur > 0 else 0
        cid = g["Type"].iloc[0]
        
        # 过滤过短的轨迹和超速跳变
        if dur > 0.5 and avg_v_kph < MAX_SPEED_MAP.get(cid, 120):
            summary.append({
                "ID": tid,
                "类别": {0:"行人", 1:"自行车", 2:"汽车"}.get(cid, "未知"),
                "总距离(m)": round(dist, 2),
                "平均速度(m/s)": round(dist/dur, 3) if dur > 0 else 0,
                "平均时速(km/h)": round(avg_v_kph, 2)
            })
    
    pd.DataFrame(summary).to_excel(os.path.join(proj_dir, "summary_report.xlsx"), index=False)
    with open(os.path.join(proj_dir, "config.json"), "w") as f:
        json.dump({"M": M_list, "rw": rw, "rh": rh, "fps": fps, "boundary": b_pts}, f)
    
    cap.release(); video_out.release(); print("\n[完成] 简表报告已生成。")

if __name__ == "__main__":
    run_processor()