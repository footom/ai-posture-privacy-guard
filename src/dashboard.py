import streamlit as st
import sqlite3
import pandas as pd
import os
import plotly.express as px

# 引入自訂設定與模組
from config import DB_FILE
import database as db

# 設定網頁標題與寬度
st.set_page_config(page_title="AI坐姿與健康防禦儀表板", layout="wide")


def load_data():
    """載入歷史日誌資料"""
    if not os.path.exists(DB_FILE):
        return None
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM behavior_logs", conn)
        conn.close()

        if df.empty:
            return df

        df['start_time'] = pd.to_datetime(df['start_time'])
        if 'end_time' in df.columns:
            df['end_time'] = pd.to_datetime(df['end_time'])

        return df
    except Exception as e:
        st.error(f"資料庫讀取出錯: {e}")
        return None


df = load_data()

# --- 網頁標頭 ---
st.title("🛡️AI資安與健康動態監控儀表板")
st.markdown("此儀表板直接同步本地端SQLite資料庫，提供即時與歷史行為數據分析。")
st.write("---")

if df is None or df.empty:
    st.warning("⚠️尚未偵測到資料庫檔案或資料庫為空。請先啟動主監控程式main.py累積數據！")
else:
    # --- 頂部摘要指標 (Key Metrics) ---
    total_events = len(df)
    good_posture_count = len(df[df['status'] == 'Good Posture'])
    good_percentage = (good_posture_count / total_events * 100) if total_events > 0 else 0
    security_alerts = len(df[df['status'].isin(['Risk (Spying)', 'Unauthorized User'])])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="📊總記錄事件數", value=f"{total_events} 筆")
    with col2:
        st.metric(label="🟢優良坐姿次數佔比", value=f"{good_percentage:.1f} %")
    with col3:
        st.metric(label="🚨資安異常觸發次數", value=f"{security_alerts} 次")
    with col4:
        # 計算健康分數
        score = db.calculate_health_score(df)
        st.metric(label="🏆今日健康分數", value=f"{score}/100")

    st.write("---")

    # --- 左右雙欄圖表版面 ---
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("📌坐姿與安全狀態比例")
        status_counts = df['status'].value_counts().reset_index()
        status_counts.columns = ['狀態', '次數']

        # 狀態配色對照表
        color_map = {
            'Good Posture': '#2ecc71',
            'Too Close': '#e74c3c',
            'Slouching': '#e67e22',
            'Risk (Spying)': '#9b59b6',
            'Verifying': '#00bcd4',
            'Unauthorized User': '#800000',
            'No Face Detected': '#f1c40f'
        }

        fig_pie = px.pie(
            status_counts,
            values='次數',
            names='狀態',
            color='狀態',
            color_discrete_map=color_map,
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with right_col:
        st.subheader("📈坐姿相對比例趨勢")
        st.markdown("比例以1.0為基準校準值。耳距過高表示距離太近；頸長過低表示出現駝背。")

        trend_df = df[['start_time', 'ear_dist_ratio', 'neck_len_ratio']].dropna()

        if not trend_df.empty:
            fig_line = px.line(
                trend_df,
                x='start_time',
                y=['ear_dist_ratio', 'neck_len_ratio'],
                labels={'value': '相對比例', 'start_time': '時間', 'variable': '指標'}
            )
            fig_line.add_hline(y=1.35, line_dash="dash", line_color="red", annotation_text="Too Close門檻 (1.35)")
            fig_line.add_hline(y=0.75, line_dash="dash", line_color="orange", annotation_text="Slouching門檻 (0.75)")
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("💡尚無足夠的坐姿基準數據可供繪製折線圖。")

    st.write("---")

    # --- 下方分析圖表 ---
    down_col1, down_col2 = st.columns(2)

    with down_col1:
        st.subheader("🕒駝背高風險時段分析")
        df["hour"] = df["start_time"].dt.hour
        slouch_df = df[df["status"] == "Slouching"]

        if not slouch_df.empty:
            hourly_slouch = slouch_df.groupby("hour").size().reset_index(name="count")
            fig_hour = px.bar(
                hourly_slouch,
                x="hour",
                y="count",
                labels={'hour': '時段(點)', 'count': '駝背次數'},
                title="各時段發生駝背累計次數"
            )
            fig_hour.update_layout(xaxis=dict(tickmode='linear', dtick=1))
            st.plotly_chart(fig_hour, use_container_width=True)
        else:
            st.info("💡目前尚無任何駝背（Slouching）的歷史記錄，工作狀態保持得非常棒！")

    with down_col2:
        st.subheader("🛡️資安威脅防禦統計")
        security_df = df[df["status"].isin(["Risk (Spying)", "Unauthorized User", "No Face Detected"])]

        if not security_df.empty:
            security_counts = security_df["status"].value_counts().reset_index()
            security_counts.columns = ['status', 'count']

            fig_security = px.bar(
                security_counts,
                x="status",
                y="count",
                color="status",
                labels={'status': '資安狀態', 'count': '觸發次數'},
                title="防護事件分布",
                color_discrete_map=color_map
            )
            st.plotly_chart(fig_security, use_container_width=True)
        else:
            st.success("🎉目前無任何資安異常與無臉偵測記錄，環境非常安全！")

    st.write("---")

    # --- 歷史明細表格 ---
    st.subheader("🗂️歷史日誌明細與過濾器")

    status_filter = st.multiselect(
        "選擇要查看的狀態：",
        options=df['status'].unique(),
        default=df['status'].unique()
    )

    filtered_df = df[df['status'].isin(status_filter)]
    filtered_df = filtered_df.sort_values(by='start_time', ascending=False)

    display_cols = ['start_time', 'end_time', 'duration_sec', 'status', 'confidence', 'ear_dist_ratio',
                    'neck_len_ratio', 'face_count']
    available_cols = [col for col in display_cols if col in filtered_df.columns]

    st.dataframe(filtered_df[available_cols], use_container_width=True)