"""Phân bổ công chăm trẻ, một trade-off thời gian scenario-gated.

Không tạo một nghề hay cơ quan riêng: chăm trẻ là một cách dùng ``cong``. Trả công, nếu
có, đi qua hợp đồng ``gop_cong`` + chuyển giao tài sản đã tồn tại; module chỉ đánh dấu
phần công của worker đã dùng cho con của bên thuê để không giao hai lần cùng một ngày.
"""

from __future__ import annotations

from engine.contracts import ben_hien_tai
from engine.ledger import LoiSoKep
from engine.spatial import _cham_tre_bat
from engine.world import World


def _ho_tre(w: World, child_id: str) -> list[str]:
    """Hộ còn sống chịu trách nhiệm cho một trẻ, theo chính quy tắc tiêu dùng của World."""
    return [aid for aid in w.ho_cua(child_id) if w.agents[aid].con_song]


def _nguoi_nhan_hop_dong_cham(w: World, carer: str, household: list[str]) -> str | None:
    """Bên thuê có clause gop_cong từ carer; dùng làm cầu nối payment contract ↔ care labor."""
    candidates: set[str] = set()
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for clause in hd.dieu_khoan:
            if clause.loai != "gop_cong":
                continue
            if ben_hien_tai(w, hd.id, clause.tu) != carer:
                continue
            recipient = ben_hien_tai(w, hd.id, clause.den)
            if recipient in household:
                candidates.add(recipient)
    return min(candidates) if candidates else None


def _dung_cong(w: World, carer: str, child: str, amount: float,
               household: list[str]) -> tuple[float, bool]:
    """Đốt tối đa ``amount`` công chăm trẻ và trả (đã chăm, có-liên-kết-trả-công)."""
    available = w.ledger.so_du(carer, "cong")
    used = min(max(0.0, amount), available)
    if used <= 1e-9:
        return 0.0, False
    try:
        w.ledger.huy(carer, "cong", used, "cham_tre", f"chăm {child}", w.tick)
    except LoiSoKep:
        return 0.0, False
    recipient = _nguoi_nhan_hop_dong_cham(w, carer, household)
    from engine.production import ghi_cong_dung

    ghi_cong_dung(w, "care", used)
    paid = recipient is not None
    if recipient is not None:
        key = (carer, recipient)
        w.cong_cham_tre_theo_cap[key] = w.cong_cham_tre_theo_cap.get(key, 0.0) + used
    return used, paid


def buoc_cham_tre(w: World, ke_hoach: dict) -> None:
    """Thực hiện chăm trẻ trước sản xuất, không mint lao động.

    Ưu tiên người tự nguyện nêu ``cham_tre_cho`` (người thân hoặc worker đã có hợp đồng
    trả công); thiếu người thì một người lớn trong hộ phải chăm. Vì vậy phụ huynh có thể
    được giải phóng đi làm, nhưng chỉ khi công của người khác thực sự bị mất đi tương ứng.
    """
    if not _cham_tre_bat(w):
        return
    cfg = w.cfg.get("khong_gian.cham_tre")
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    age_need = float(cfg["tuoi_can_cham"])
    labor_per_child = float(cfg["cong_cham_moi_tre"])
    children = [
        a.id for a in w.agents.values()
        if a.con_song and a.tuoi_nam < age_need
    ]
    remaining = {cid: labor_per_child for cid in sorted(children)}
    total_provided = paid_provided = kin_or_parent = 0.0

    # 1) Lựa chọn tự nguyện explicit: người chăm có thể là họ hàng, hàng xóm hay người
    # đã nhận gop_cong từ phụ huynh. Một child chỉ được trừ đúng nhu cầu còn lại.
    for carer in sorted(ke_hoach):
        person = w.agents.get(carer)
        if person is None or not person.con_song or person.tuoi_nam < adult_age:
            continue
        targets = list(dict.fromkeys(str(cid) for cid in ke_hoach[carer].cham_tre_cho))
        for child in targets:
            need = remaining.get(child, 0.0)
            if need <= 1e-9:
                continue
            household = _ho_tre(w, child)
            if not household or carer == child:
                continue
            used, paid = _dung_cong(w, carer, child, need, household)
            if used <= 0:
                continue
            remaining[child] -= used
            total_provided += used
            paid_provided += used if paid else 0.0
            kin_or_parent += used if not paid else 0.0
            w.events.ghi(w.tick, "cham_tre", carer=carer, tre=child,
                         cong=round(used, 3), paid=paid)

    # 2) Không có người nhận chăm đủ: hộ tự phân công. Chọn người còn nhiều công nhất để
    # không ngầm ưu ái giới/ID, tie-break id giữ determinism.
    for child in sorted(remaining):
        need = remaining[child]
        if need <= 1e-9:
            continue
        household = _ho_tre(w, child)
        adults = [
            aid for aid in household
            if w.agents[aid].tuoi_nam >= adult_age and aid != child
        ]
        adults.sort(key=lambda aid: (-w.ledger.so_du(aid, "cong"), aid))
        for carer in adults:
            if need <= 1e-9:
                break
            used, _paid = _dung_cong(w, carer, child, need, household)
            if used <= 0:
                continue
            need -= used
            remaining[child] -= used
            total_provided += used
            kin_or_parent += used
            w.events.ghi(w.tick, "cham_tre", carer=carer, tre=child,
                         cong=round(used, 3), paid=False, tu_cham=True)

    demand = labor_per_child * len(children)
    w.cham_tre_tick = {
        "demand": round(demand, 6),
        "provided": round(total_provided, 6),
        "paid": round(paid_provided, 6),
        "kin_or_parent": round(kin_or_parent, 6),
        "unmet": round(sum(max(0.0, x) for x in remaining.values()), 6),
    }
