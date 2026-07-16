"""Dashboard streamlit 6 tab (SPEC 10) — chỉ đọc log/checkpoint.

  streamlit run viz/dashboard.py -- --run mock300
"""

from __future__ import annotations

import json
import pickle
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"


def chon_run() -> str:
    runs = sorted(d.name for d in DATA_DIR.iterdir()
                  if (d / "metrics.jsonl").exists()) if DATA_DIR.exists() else []
    mac_dinh = "mock300" if "mock300" in runs else (runs[0] if runs else "")
    if "--run" in sys.argv:
        mac_dinh = sys.argv[sys.argv.index("--run") + 1]
    return st.sidebar.selectbox("Run", runs, index=runs.index(mac_dinh) if mac_dinh in runs else 0)


@st.cache_data
def doc_metrics(run: str) -> pd.DataFrame:
    return pd.DataFrame(
        json.loads(x) for x in open(DATA_DIR / run / "metrics.jsonl", encoding="utf-8")
    )


@st.cache_data
def doc_events(run: str, loai: tuple[str, ...]) -> list[dict]:
    ket_qua = []
    for line in open(DATA_DIR / run / "events.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if e["loai"] in loai:
            ket_qua.append(e)
    return ket_qua


def main() -> None:
    st.set_page_config(page_title="THÓC", layout="wide")
    run = chon_run()
    df = doc_metrics(run)
    st.title(f"THÓC — {run}")

    tab_map, tab_kt, tab_xh, tab_hd, tab_quota, tab_su_kien = st.tabs(
        ["Bản đồ", "Kinh tế", "Xã hội", "Hợp đồng", "Token/Quota", "Dòng sự kiện"]
    )

    with tab_map:
        cks = sorted((DATA_DIR / run / "checkpoints").glob("checkpoint_0*.pkl"))
        if cks:
            chon = st.select_slider("Checkpoint (tick)", options=[c.stem[-4:] for c in cks],
                                    value=cks[-1].stem[-4:])
            w = pickle.load(open(DATA_DIR / run / "checkpoints" / f"checkpoint_{chon}.pkl", "rb"))
            h = max(p.r for p in w.parcels.values()) + 1
            wd = max(p.c for p in w.parcels.values()) + 1
            mau = {"ruong": [46, 110, 50], "rung": [24, 70, 30], "doi": [110, 95, 70],
                   "mo_dong": [140, 120, 60], "song": [50, 90, 160]}
            import numpy as np

            anh = np.zeros((h, wd, 3), dtype=int)
            for p in w.parcels.values():
                c = mau.get(p.loai, [40, 40, 40])
                if p.chu and p.chu.startswith("E"):
                    c = [255, 0, 255]
                elif p.chu:
                    c = [200, 60, 60]
                anh[p.r, p.c] = c
            st.image(anh.astype("uint8"), width=650,
                     caption="đỏ = đất tư, tím = đất pháp nhân")
            st.write(f"Máy: {w.ledger.tong_tai_san('may'):.0f} · "
                     f"Entity hoạt động: {sum(1 for e in w.entities.values() if e.con_hoat_dong)}")

    with tab_kt:
        c1, c2 = st.columns(2)
        c1.line_chart(df.set_index("nam")[["gini_dat", "gini_thoc"]])
        if "n_thua_tu_huu" in df and df["gini_dat"].isna().any():
            c1.caption("Gini đất = missing khi không có thửa tư hữu; không được đọc là bình đẳng 0.")
        c1.line_chart(df.set_index("nam")[["thoc_moi_nguoi"]])
        c2.line_chart(df.set_index("nam")[["kl_giao_dich"]])
        if "so_may" in df:
            c2.line_chart(df.set_index("nam")[["so_may", "so_entity"]])
        if "gdp_price_coverage" in df:
            latest_coverage = df["gdp_price_coverage"].iloc[-1]
            if isinstance(latest_coverage, dict):
                c2.caption(
                    "GDP price coverage (ledger components, tick cuối): "
                    f"{latest_coverage.get('priced_components', 0)}/"
                    f"{latest_coverage.get('components', 0)}."
                )

    with tab_xh:
        c1, c2 = st.columns(2)
        c1.line_chart(df.set_index("nam")[["dan_so", "vo_gia_cu"]])
        c1.line_chart(df.set_index("nam")[["ty_le_biet_chu"]])
        if "tri_thuc" in df:
            c2.line_chart(df.set_index("nam")[["tri_thuc"]])
        gc = pd.DataFrame(list(df["giai_cap"].fillna({}).values)).fillna(0)
        gc["nam"] = df["nam"].values
        c2.area_chart(gc.set_index("nam"))

    with tab_hd:
        st.caption("Mô-típ = tổ hợp điều khoản (auto-cluster) — cửa sổ nhìn định chế tự phát")
        ky = doc_events(run, ("ky_hd",))
        motif_theo_nam = Counter((e["tick"] // 40 * 20, e["mo_tip"]) for e in ky)
        if motif_theo_nam:
            dfm = pd.DataFrame(
                [{"nam": k[0], "mo_tip": k[1], "so": v} for k, v in motif_theo_nam.items()]
            ).pivot_table(index="nam", columns="mo_tip", values="so", fill_value=0)
            st.area_chart(dfm)
        st.line_chart(df.set_index("nam")[["hd_hieu_luc", "so_mo_tip"]])
        nhan = doc_events(run, ("nhan_dinh_che",))
        if nhan:
            st.dataframe(pd.DataFrame(nhan[-50:]))

    with tab_quota:
        db = DATA_DIR / run / "llm_calls.sqlite"
        if db.exists():
            conn = sqlite3.connect(db)
            dfc = pd.read_sql_query(
                "SELECT tick, tier, provider, model, batch_size, tok_in, tok_out,"
                " latency_ms, retries, fallback FROM llm_calls", conn)
            st.write(f"Tổng call: {len(dfc)} · fallback: {dfc['fallback'].sum()} "
                     f"({dfc['fallback'].mean():.2%})")
            st.bar_chart(dfc.groupby("model")["tok_out"].sum())
            st.line_chart(dfc.groupby(dfc["tick"] // 20 * 20)["fallback"].mean())
        else:
            st.info("Run này không có llm_calls (mode rulebot).")

    with tab_su_kien:
        loai = st.multiselect("Loại sự kiện", ["milestone", "chronicle", "lap_entity",
                                               "blueprint_moi", "hang_moi", "pha_san_entity",
                                               "vi_pham", "di_cu", "ban_dat"],
                              default=["milestone", "chronicle"])
        if loai:
            evs = doc_events(run, tuple(loai))
            st.dataframe(pd.DataFrame(evs[-300:]))


main()
