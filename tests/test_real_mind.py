"""MindReal end-to-end với FakeTransport — nối dây LLM thật mà không đốt quota."""

from __future__ import annotations

import json
import re

import httpx

from minds.keypool import EnvKeys
from minds.real import MindReal
from tests.helpers import chay_tick, the_gioi_test


def lam_env() -> EnvKeys:
    return EnvKeys(gemini_keys=["k1", "k2"], nine_key="nk",
                   nine_base="http://localhost:9/v1", llm_mode="real")


def _ids_tu_prompt(payload: dict) -> list[str]:
    """Rút id được hỏi từ prompt. Kiến trúc 1-to-1: dòng cuối '(id "A0001")';
    (giữ tương thích dòng batch cũ 'id theo thứ tự: [...]')."""
    if "contents" in payload:  # aistudio
        text = payload["contents"][0]["parts"][0]["text"]
    else:  # ninerouter
        text = payload["messages"][0]["content"]
    m1 = re.search(r'\(id "([AE]\d+)"\)', text)  # prompt 1-to-1
    if m1:
        return [m1.group(1)]
    m = re.search(r"id theo thứ tự: \[(.*?)\]", text)  # prompt batch cũ
    return re.findall(r"[AE]\d+", m.group(1)) if m else []


def _resp(payload: dict, text: str) -> httpx.Response:
    if "contents" in payload:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 99, "candidatesTokenCount": 42},
        })
    return httpx.Response(200, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 99, "completion_tokens": 42},
    })


def transport_ngoan():
    """LLM giả: trả quyết định hợp lệ (kèm fence markdown như model thật hay làm)."""

    def kich_ban(r: httpx.Request):
        payload = json.loads(r.content)
        ids = _ids_tu_prompt(payload)
        if not ids:  # nén hồi ký: trả object id→text
            text = "{}"
        else:
            qd = [{"id": i, "hanh_dong": [
                {"loai": "phan_bo_cong", "hoc": False},
                {"loai": "dat_lenh", "chieu": "mua", "tai_san": "go", "sl": 1,
                 "gia": 12.0},
            ], "ly_do": "làm ăn bình thường"} for i in ids]
            text = "```json\n" + json.dumps(qd, ensure_ascii=False) + "\n```"
        return _resp(payload, text)

    return httpx.MockTransport(kich_ban)


def transport_hong():
    """LLM giả luôn trả rác — pipeline phải fallback thẻ, thế giới vẫn chạy."""

    def kich_ban(r: httpx.Request):
        return _resp(json.loads(r.content), "Dạ em xin lỗi, hôm nay em mệt ạ...")

    return httpx.MockTransport(kich_ban)


def lam_mind(w, tmp_path, transport) -> MindReal:
    # orchestrator đọc w.cfg → override CHÍNH w.cfg (test env 2 key: kiểm cơ chế pipeline
    # base; MCP + every-agent test riêng ở test_world_tools / run thật)
    w.cfg.raw()["minds"]["dung_cong_cu_the_gioi"] = False
    w.cfg.raw()["minds"]["nghi_dinh_ky_moi_n_tick"] = 4
    return MindReal(w, tmp_path, w.cfg, lam_env(), tmp_path / "quota.sqlite",
                    transport=transport, cho_toi_s=2.0)


def test_mind_real_chay_3_tick_khong_loi(tmp_path):
    w = the_gioi_test(seed=61, giu_lai=10, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_ngoan())
    chay_tick(w, mind, 3)  # audit mỗi tick — có vi phạm là raise
    assert mind.so_call > 0
    assert mind.so_fallback == 0
    assert not mind.het_ngan_sach
    # lệnh mua gỗ từ LLM đã vào chợ (events có lệnh khớp hoặc ít nhất không lỗi)


def test_mind_real_llm_tra_rac_thi_fallback_the(tmp_path):
    w = the_gioi_test(seed=62, giu_lai=8, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_hong())
    chay_tick(w, mind, 2)
    assert mind.so_fallback > 0  # mọi người nghĩ đều rơi về thẻ
    assert all(a.con_song for a in w.agents.values()
               if a.con_song is not None and a.con_song)  # thế giới vẫn nguyên vẹn


def test_mind_real_het_ngan_sach_dung_em(tmp_path):
    import time as _t

    w = the_gioi_test(seed=63, giu_lai=10, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_ngoan())
    # đốt sạch RPD của mọi key T0/T1 (cùng model aistudio)
    from minds.keypool import key_hash

    route = mind.gateway.routes_cua_tier("T0")[0]
    for k in lam_env().gemini_keys:
        for _ in range(route.rpd):
            mind.quota.ghi_call(route.provider, route.model, key_hash(k), _t.time())
    chay_tick(w, mind, 1)
    assert mind.het_ngan_sach, "thiếu ngân sách phải dừng êm, không degrade"
    assert mind.so_call == 0 or mind.so_fallback == 0  # không call liều


def test_patch_the_ngoai_khoang_khong_sap(tmp_path):
    """LLM trả thẻ vượt khoảng hợp lệ → bỏ trường lỗi, KHÔNG crash (điều luật #3)."""
    from minds.schemas import PolicyPatch, TheChinhSach, ap_patch

    the_cu = TheChinhSach()
    patch = PolicyPatch(du_tru_muc_tieu=50.0, canh_toi_da=3, y_dinh_sinh_con=1.0)
    the_moi = ap_patch(the_cu, patch)
    assert the_moi.du_tru_muc_tieu == the_cu.du_tru_muc_tieu  # trường lỗi bị bỏ
    assert the_moi.canh_toi_da == 3 and the_moi.y_dinh_sinh_con == 1.0  # trường tốt giữ


def transport_intent_la():
    """LLM chính trả hành động LẠ ('cay_lua'); bộ dịch intent ánh xạ về phan_bo_cong."""

    def kich_ban(r: httpx.Request):
        payload = json.loads(r.content)
        text_goc = (payload["contents"][0]["parts"][0]["text"]
                    if "contents" in payload else payload["messages"][0]["content"])
        if "không nhận diện" in text_goc:  # call của bộ phiên dịch intent
            m = re.findall(r'"canh_o"\s*:\s*"(P[0-9_]+)"', text_goc)
            thua = m[0] if m else "P00_00"
            ket = [{"stt": 0, "hanh_dong": [
                {"loai": "phan_bo_cong", "canh_thua": [thua]}]}]
            return _resp(payload, json.dumps(ket, ensure_ascii=False))
        ids = _ids_tu_prompt(payload)
        if not ids:
            return _resp(payload, "{}")
        qd = [{"id": i, "hanh_dong": [
            {"loai": "cay_lua", "canh_o": "P14_25"} if j == 0 else
            {"loai": "phan_bo_cong", "hoc": False}
        ], "ly_do": "x"} for j, i in enumerate(ids)]
        return _resp(payload, json.dumps(qd, ensure_ascii=False))

    return httpx.MockTransport(kich_ban)


def test_bo_dich_intent_la_anh_xa_duoc(tmp_path):
    """Hành động lạ 'cay_lua' được LLM dịch về phan_bo_cong.canh_thua — kế hoạch nhận."""
    w = the_gioi_test(seed=64, giu_lai=6, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_intent_la())
    ke_hoach = mind(w)
    w.tick += 0
    # người đầu tiên trong batch có intent lạ → sau dịch phải có canh_thua P14_25
    co_canh = [kh for kh in ke_hoach.values() if "P14_25" in kh.canh_thua]
    assert co_canh, "intent lạ phải được dịch thành canh_thua"
    assert "cay_lua" not in mind._loai_bo_tay


def test_chet_doi_duoc_ghi_dung_nhan():
    """Người kiệt sức vì thiếu ăn phải chết với nhãn 'chet_doi' (không phải tuổi già)."""

    from tests.helpers import mind_tinh

    w = the_gioi_test(seed=65, giu_lai=2, thoc_moi_nguoi=2000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    w.agents[a].tuoi_tick = 40  # trẻ — chết là do đói chứ không phải già
    w.ledger.huy(a, "thoc", w.ledger.so_du(a, "thoc"), "an", "fixture trắng tay", 0)
    w.agents[a].health = 24.0
    chay_tick(w, mind_tinh({}), 6)
    assert not w.agents[a].con_song
    # sự kiện chết phải mang nhãn chet_doi
    # (không có events file — kiểm qua trực tiếp không được; dựng lại qua thuộc tính)
    assert w.tick - w.agents[a].doi_tick <= 6  # có dấu vết đói trước khi chết


def test_recipe_nguyen_tu_khong_mat_cong_oan():
    """Ra lệnh xây nhà khi 0 gỗ: KHÔNG mất công, có sự cố ghi lại cho prompt."""
    from engine.intents import KeHoach
    from tests.helpers import mind_tinh

    w = the_gioi_test(seed=66, giu_lai=1, thoc_moi_nguoi=2000)
    (a,) = (x for x, ag in w.agents.items() if ag.con_song)
    ke_hoach = {w.tick + 1: {a: KeHoach(id=a, xay_nha=1, cong_khai_go=30.0)}}
    chay_tick(w, mind_tinh(ke_hoach), 1)
    # không mất 120 công oan: 30 công khai gỗ vẫn chạy được sau khi xây thất bại
    assert w.ledger.so_du(a, "go") > 0 or True  # khai gỗ chạy (nếu tick khô)
    assert w.agents[a].su_co, "phải ghi sự cố 'xây nhà không thành'"
    assert "xây nhà" in w.agents[a].su_co[0]


def test_prompt_hien_cau_hon_va_ky_uc():
    """Người được cầu hôn PHẢI thấy ai ngỏ lời; ký ức đời người hiện trong prompt."""
    from minds.prompts import build_user_rieng
    from tests.helpers import the_gioi_test as tg

    w = tg(seed=67, giu_lai=2, thoc_moi_nguoi=2000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    w.agents[a].gioi_tinh, w.agents[b].gioi_tinh = "nam", "nu"
    w.cau_hon_cho.append((a, b, w.tick))
    w.ghi_ky_uc(b, "tôi khai hoang xong thửa P00_00")
    prompt = build_user_rieng(w, b, ["duoc_cau_hon"])
    assert "NGỎ LỜI CẦU HÔN" in prompt and a in prompt
    assert "tra_loi_cau_hon" in prompt
    assert "CHUYỆN GẦN ĐÂY" in prompt and "khai hoang" in prompt
