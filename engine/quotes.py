"""Versioned A2A quote/escrow protocol for ``spatial_livelihood_v2``.

This is not a price-setting institution: a participant chooses an ask/bid, quantity and
payment asset. The engine only validates physical/accounting feasibility, holds escrow and
settles the bilateral exchange exactly once. The legacy call auction and contract board keep
working unchanged when the scenario gate is off.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from engine.ledger import EPSILON, ButToan, LoiSoKep, Transaction

ESCROW_PREFIX = "KY_QUY:"


def _cfg(x: Any) -> Any:
    return getattr(x, "cfg", x)


def _bao_gia_bat(x: Any) -> bool:
    cfg = _cfg(x)
    return bool(cfg.get("thuong_mai.bao_gia.bat", False))


def _holder(quote_id: str) -> str:
    return f"{ESCROW_PREFIX}{quote_id}"


def _holder_doi_tac(quote_id: str, aid: str, index: int) -> str:
    return f"{ESCROW_PREFIX}{quote_id}:{aid}:{index}"


@dataclass
class QuoteFill:
    """Một phần quote đã được chấp nhận; hai escrow tách biệt cho delivery future."""

    buyer: str
    seller: str
    quantity: float
    due_tick: int
    counterparty_holder: str
    counterparty_asset: str
    counterparty_amount: float
    status: str = "pending"  # pending | settled | failed
    tick_settle: int | None = None


@dataclass
class BaoGia:
    id: str
    nguoi_dang: str
    doi_tac: str | None
    chieu: str  # ban = ask, mua = bid
    tai_san: str
    so_luong: float
    con_lai: float
    don_gia: float
    thanh_toan: str
    het_han_tick: int
    giao_tai: str
    lang: int
    bo: str | None
    tick_dang: int
    trang_thai: str = "dang_treo"  # dang_treo | da_khop | hoan_thanh | het_han | da_huy
    tick_settle: int | None = None
    escrow: dict[str, float] = field(default_factory=dict)  # main-holder balances declared
    fills: list[QuoteFill] = field(default_factory=list)


def _asset_main(q: BaoGia) -> tuple[str, float]:
    if q.chieu == "ban":
        return q.tai_san, q.so_luong
    return q.thanh_toan, q.so_luong * q.don_gia


def _amount_main_for_fill(q: BaoGia, fill: QuoteFill) -> float:
    return fill.quantity if q.chieu == "ban" else fill.quantity * q.don_gia


def _record_failure(w: Any, aid: str, code: str, detail: str) -> None:
    """Actionable local feedback without treating a rejected intent as execution."""
    a = w.agents.get(aid)
    if a is not None and a.con_song:
        a.su_co = [*a.su_co, f"[{code}] {detail}"][-3:]
    w.events.ghi(w.tick, "bao_gia_tu_choi", ai=aid, code=code, chi_tiet=detail)


def _agent_lang_bo(w: Any, aid: str) -> tuple[int, str | None]:
    from engine.spatial import _bo_cua

    a = w.agents.get(aid)
    lang = a.lang if a is not None else 0
    return int(lang), _bo_cua(w, aid)


def _parse_due(w: Any, raw: Any) -> tuple[str, int] | None:
    if raw in (None, "", "ngay"):
        return "ngay", w.tick
    text = str(raw)
    if not text.startswith("tick:"):
        return None
    try:
        due = int(text.split(":", 1)[1])
    except ValueError:
        return None
    if due <= w.tick:
        return None
    return text, due


def _visible(w: Any, aid: str, q: BaoGia) -> bool:
    if q.doi_tac is not None and q.doi_tac != aid:
        return False
    if not w.chu_the_hoat_dong(aid) or aid == q.nguoi_dang:
        return False
    from engine.market import _toi_duoc_cho

    return _toi_duoc_cho(w, aid, q.lang)


def quote_visible_to(w: Any, aid: str) -> list[BaoGia]:
    """Read-only local-information view; only currently accept-able quote threads."""
    if not _bao_gia_bat(w):
        return []
    return [
        q for _qid, q in sorted(getattr(w, "bao_gia", {}).items())
        if q.trang_thai == "dang_treo" and q.con_lai > EPSILON and _visible(w, aid, q)
    ]


def _new_id(w: Any) -> str:
    w._next_bao_gia = int(getattr(w, "_next_bao_gia", 0)) + 1
    return f"BG{w._next_bao_gia:05d}"


def _post(w: Any, aid: str, raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        _record_failure(w, aid, "bad_params", "báo giá phải là object")
        return
    try:
        chieu = str(raw.get("chieu", ""))
        tai_san = str(raw.get("tai_san", ""))
        quantity = float(raw.get("so_luong", 0.0))
        price = float(raw.get("don_gia", raw.get("gia", 0.0)))
        payment = str(raw.get("thanh_toan", "thoc"))
    except (TypeError, ValueError):
        _record_failure(w, aid, "bad_params", "không đọc được lượng hoặc đơn giá")
        return
    if (chieu not in {"ban", "mua"} or not tai_san or not payment or payment == tai_san
            or not math.isfinite(quantity) or not math.isfinite(price)
            or quantity <= EPSILON or price <= EPSILON):
        _record_failure(w, aid, "bad_params", "chiều, tài sản, lượng hoặc đơn giá không hợp lệ")
        return
    doi_tac_raw = raw.get("doi_tac")
    doi_tac = str(doi_tac_raw) if doi_tac_raw not in (None, "", "*") else None
    if doi_tac is not None and (doi_tac == aid or not w.chu_the_hoat_dong(doi_tac)):
        _record_failure(w, aid, "counterparty_unavailable", "đối tác đích danh không hoạt động")
        return
    parsed_due = _parse_due(w, raw.get("giao_tai", "ngay"))
    if parsed_due is None:
        _record_failure(w, aid, "bad_params", "giao_tai phải là ngay hoặc tick lớn hơn tick hiện tại")
        return
    delivery, _due = parsed_due
    ttl = int(w.cfg.get("thuong_mai.bao_gia.het_han_tick", 1))
    requested_expiry = raw.get("het_han_tick")
    if requested_expiry is None:
        expiry = w.tick + max(1, ttl)
    else:
        try:
            expiry = int(requested_expiry)
        except (TypeError, ValueError):
            _record_failure(w, aid, "bad_params", "het_han_tick không phải số nguyên")
            return
        if expiry <= w.tick:
            _record_failure(w, aid, "expired_quote", "hạn báo giá phải ở tương lai")
            return

    quote_id = _new_id(w)
    lang, bo = _agent_lang_bo(w, aid)
    q = BaoGia(
        id=quote_id, nguoi_dang=aid, doi_tac=doi_tac, chieu=chieu, tai_san=tai_san,
        so_luong=quantity, con_lai=quantity, don_gia=price, thanh_toan=payment,
        het_han_tick=expiry, giao_tai=delivery, lang=lang, bo=bo, tick_dang=w.tick,
    )
    asset, amount = _asset_main(q)
    try:
        w.ledger.chuyen(aid, _holder(quote_id), asset, amount, f"ký quỹ báo giá {quote_id}", w.tick)
    except LoiSoKep:
        _record_failure(w, aid, "insufficient_inventory", f"không đủ {asset} để ký quỹ")
        return
    q.escrow = {asset: amount}
    w.bao_gia[quote_id] = q
    w.events.ghi(
        w.tick, "bao_gia_dang", id=quote_id, ai=aid, chieu=chieu, tai_san=tai_san,
        so_luong=round(quantity, 9), don_gia=round(price, 9), thanh_toan=payment,
        het_han_tick=expiry, giao_tai=delivery, doi_tac=doi_tac, lang=lang,
    )


def _settle_fill(w: Any, q: BaoGia, fill: QuoteFill) -> bool:
    if fill.status != "pending":
        return False
    main_holder = _holder(q.id)
    asset_holder = main_holder if q.chieu == "ban" else fill.counterparty_holder
    payment_holder = fill.counterparty_holder if q.chieu == "ban" else main_holder
    payment = fill.quantity * q.don_gia
    try:
        w.ledger.ap_dung(Transaction(
            tick=w.tick,
            ly_do=f"thanh toán báo giá {q.id}",
            but_toan=(
                ButToan(asset_holder, q.tai_san, -fill.quantity),
                ButToan(fill.buyer, q.tai_san, fill.quantity),
                ButToan(payment_holder, q.thanh_toan, -payment),
                ButToan(fill.seller, q.thanh_toan, payment),
            ),
        ))
    except LoiSoKep:
        # A settlement failure must never strand the counterparty's escrow. In
        # normal operation this branch is unreachable (both sides were locked
        # before the fill existed), but it is a fail-closed recovery path for a
        # corrupt/stale checkpoint rather than a silent asset sink.
        main_asset, _main_total = _asset_main(q)
        poster_refund = min(
            _amount_main_for_fill(q, fill), w.ledger.so_du(main_holder, main_asset)
        )
        acceptor = fill.buyer if q.chieu == "ban" else fill.seller
        counter_refund = min(
            fill.counterparty_amount,
            w.ledger.so_du(fill.counterparty_holder, fill.counterparty_asset),
        )
        try:
            if poster_refund > EPSILON:
                w.ledger.chuyen(main_holder, q.nguoi_dang, main_asset, poster_refund,
                                 f"hoàn ký quỹ báo giá lỗi {q.id}", w.tick)
            if counter_refund > EPSILON:
                w.ledger.chuyen(fill.counterparty_holder, acceptor, fill.counterparty_asset,
                                 counter_refund, f"hoàn ký quỹ đối tác lỗi {q.id}", w.tick)
        except LoiSoKep:
            # Audit below will surface any further corruption. Never mint a
            # compensating balance merely to make an invalid checkpoint green.
            pass
        actual_main = w.ledger.so_du(main_holder, main_asset)
        q.escrow = {main_asset: actual_main} if actual_main > EPSILON else {}
        fill.counterparty_amount = w.ledger.so_du(
            fill.counterparty_holder, fill.counterparty_asset
        )
        _record_failure(w, fill.buyer if q.chieu == "ban" else fill.seller,
                        "escrow_failed", f"ký quỹ {q.id} không đủ khi giao")
        fill.status = "failed"
        w.events.ghi(w.tick, "bao_gia_that_bai", id=q.id,
                     hoan_nguoi_dang=round(poster_refund, 9),
                     hoan_doi_tac=round(counter_refund, 9))
        return False
    main_asset, _ = _asset_main(q)
    q.escrow[main_asset] = max(0.0, q.escrow.get(main_asset, 0.0) - _amount_main_for_fill(q, fill))
    if q.escrow[main_asset] <= EPSILON:
        q.escrow.pop(main_asset, None)
    fill.counterparty_amount = 0.0
    fill.status = "settled"
    fill.tick_settle = w.tick
    w.ghi_gia(q.tai_san, q.don_gia, fill.quantity, q.thanh_toan)
    gia_tt = 1.0 if q.thanh_toan == "thoc" else (w.gia_gan_nhat(q.thanh_toan) or 0.0)
    w.kl_thanh_toan_tick[q.thanh_toan] = (
        w.kl_thanh_toan_tick.get(q.thanh_toan, 0.0) + payment * gia_tt
    )
    w.events.ghi(w.tick, "bao_gia_thanh_toan", id=q.id, mua=fill.buyer, ban=fill.seller,
                 so_luong=round(fill.quantity, 9), don_gia=round(q.don_gia, 9),
                 thanh_toan=q.thanh_toan)
    w.ghi_ky_uc(
        fill.buyer,
        f"báo giá {q.id} đã giao: nhận {fill.quantity:g} {q.tai_san} giá {q.don_gia:g} {q.thanh_toan}",
    )
    w.ghi_ky_uc(
        fill.seller,
        f"báo giá {q.id} đã giao: bán {fill.quantity:g} {q.tai_san} giá {q.don_gia:g} {q.thanh_toan}",
    )
    return True


def _accept(w: Any, aid: str, raw: dict[str, Any]) -> None:
    if not isinstance(raw, dict):
        _record_failure(w, aid, "bad_params", "chấp nhận báo giá phải là object")
        return
    quote_id = str(raw.get("ref", raw.get("id", "")))
    q = w.bao_gia.get(quote_id)
    if q is None:
        _record_failure(w, aid, "offer_not_found", "không có báo giá này")
        return
    if q.trang_thai != "dang_treo" or q.con_lai <= EPSILON:
        _record_failure(w, aid, "quote_exhausted", "báo giá đã hết hoặc đã đóng")
        return
    if w.tick > q.het_han_tick:
        _record_failure(w, aid, "expired_quote", "báo giá đã hết hạn")
        return
    if not _visible(w, aid, q):
        _record_failure(w, aid, "offer_not_visible", "báo giá không dành cho bạn hoặc không tới được")
        return
    try:
        quantity = float(raw.get("so_luong", q.con_lai))
    except (TypeError, ValueError):
        _record_failure(w, aid, "bad_params", "lượng chấp nhận không hợp lệ")
        return
    if not math.isfinite(quantity) or quantity <= EPSILON:
        _record_failure(w, aid, "bad_params", "lượng chấp nhận phải dương")
        return
    quantity = min(quantity, q.con_lai)
    seller, buyer = (q.nguoi_dang, aid) if q.chieu == "ban" else (aid, q.nguoi_dang)
    cp_asset = q.thanh_toan if q.chieu == "ban" else q.tai_san
    cp_amount = quantity * q.don_gia if q.chieu == "ban" else quantity
    fill_index = len(q.fills) + 1
    cp_holder = _holder_doi_tac(q.id, aid, fill_index)
    try:
        w.ledger.chuyen(aid, cp_holder, cp_asset, cp_amount,
                         f"ký quỹ chấp nhận báo giá {q.id}", w.tick)
    except LoiSoKep:
        _record_failure(w, aid, "insufficient_payment", f"không đủ {cp_asset} để chấp nhận")
        return
    _delivery, due = _parse_due(w, q.giao_tai) or ("ngay", w.tick)
    fill = QuoteFill(
        buyer=buyer, seller=seller, quantity=quantity, due_tick=due,
        counterparty_holder=cp_holder, counterparty_asset=cp_asset,
        counterparty_amount=cp_amount,
    )
    q.fills.append(fill)
    q.con_lai = max(0.0, q.con_lai - quantity)
    w.events.ghi(w.tick, "bao_gia_khop", id=q.id, ben_nhan=aid,
                 so_luong=round(quantity, 9), con_lai=round(q.con_lai, 9))
    if due <= w.tick:
        _settle_fill(w, q, fill)
    if q.con_lai <= EPSILON:
        q.trang_thai = "da_khop"
    _cap_nhat_trang_thai(w, q)


def _pending_main(q: BaoGia) -> float:
    return sum(_amount_main_for_fill(q, fill) for fill in q.fills if fill.status == "pending")


def _release_unallocated(w: Any, q: BaoGia, loai: str) -> None:
    holder = _holder(q.id)
    main_asset, _ = _asset_main(q)
    balance = w.ledger.so_du(holder, main_asset)
    refund = max(0.0, balance - _pending_main(q))
    if refund > EPSILON:
        w.ledger.chuyen(holder, q.nguoi_dang, main_asset, refund,
                         f"hoàn ký quỹ báo giá {q.id}", w.tick)
    pending = _pending_main(q)
    q.escrow = {main_asset: pending} if pending > EPSILON else {}
    w.events.ghi(w.tick, loai, id=q.id, hoan=round(refund, 9), tai_san=main_asset)


def _cancel(w: Any, aid: str, quote_id: str) -> None:
    q = w.bao_gia.get(quote_id)
    if q is None:
        _record_failure(w, aid, "offer_not_found", "không có báo giá này")
        return
    if q.nguoi_dang != aid:
        _record_failure(w, aid, "not_authorized", "chỉ người đăng mới được hủy báo giá")
        return
    if q.trang_thai not in {"dang_treo", "da_khop"}:
        _record_failure(w, aid, "quote_closed", "báo giá đã đóng")
        return
    q.con_lai = 0.0
    q.trang_thai = "da_huy"
    _release_unallocated(w, q, "bao_gia_huy")
    _cap_nhat_trang_thai(w, q)


def _cancel_for_death(w: Any, q: BaoGia, aid: str) -> None:
    """Release every pending escrow before the estate of a dead party opens."""
    if q.trang_thai not in {"dang_treo", "da_khop"}:
        return
    main_holder = _holder(q.id)
    main_asset, _main_total = _asset_main(q)
    for fill in q.fills:
        if fill.status != "pending":
            continue
        main_amount = _amount_main_for_fill(q, fill)
        main_refund = min(main_amount, w.ledger.so_du(main_holder, main_asset))
        acceptor = fill.buyer if q.chieu == "ban" else fill.seller
        counter_refund = min(
            fill.counterparty_amount,
            w.ledger.so_du(fill.counterparty_holder, fill.counterparty_asset),
        )
        try:
            if main_refund > EPSILON:
                w.ledger.chuyen(main_holder, q.nguoi_dang, main_asset, main_refund,
                                 f"hoàn ký quỹ báo giá tử vong {q.id}", w.tick)
            if counter_refund > EPSILON:
                w.ledger.chuyen(fill.counterparty_holder, acceptor, fill.counterparty_asset,
                                 counter_refund, f"hoàn ký quỹ đối tác tử vong {q.id}", w.tick)
        except LoiSoKep:
            # Do not manufacture a compensating balance. The quote audit will
            # expose an already-corrupt ledger, while valid escrows always take
            # this deterministic release path.
            pass
        fill.counterparty_amount = w.ledger.so_du(fill.counterparty_holder, fill.counterparty_asset)
        fill.status = "failed"
    q.con_lai = 0.0
    q.trang_thai = "da_huy"
    _release_unallocated(w, q, "bao_gia_huy_tu_vong")
    _cap_nhat_trang_thai(w, q)
    w.events.ghi(w.tick, "bao_gia_huy_tu_vong", id=q.id, ai=aid)


def xu_ly_nguoi_chet(w: Any, aid: str) -> None:
    """Cancel future bilateral promises before inheritance sees a dead ledger owner."""
    if not _bao_gia_bat(w):
        return
    for _quote_id, quote in sorted(w.bao_gia.items()):
        parties = {quote.nguoi_dang, quote.doi_tac}
        for fill in quote.fills:
            parties |= {fill.buyer, fill.seller}
        if aid in parties:
            _cancel_for_death(w, quote, aid)


def _expire(w: Any) -> None:
    for _qid, q in sorted(w.bao_gia.items()):
        if q.trang_thai == "dang_treo" and w.tick > q.het_han_tick:
            q.con_lai = 0.0
            q.trang_thai = "het_han"
            _release_unallocated(w, q, "bao_gia_het_han")
            _cap_nhat_trang_thai(w, q)


def _cap_nhat_trang_thai(w: Any, q: BaoGia) -> None:
    pending = [fill for fill in q.fills if fill.status == "pending"]
    if pending:
        return
    if q.trang_thai == "da_khop" and q.con_lai <= EPSILON:
        q.trang_thai = "da_huy" if any(fill.status == "failed" for fill in q.fills) else "hoan_thanh"
        q.tick_settle = w.tick
    elif q.trang_thai in {"da_huy", "het_han"}:
        q.tick_settle = w.tick


def buoc_bao_gia(w: Any, ke_hoach: dict[str, Any]) -> None:
    """Quote state machine phase: cancel → expiry → post → accept, all deterministic."""
    if not _bao_gia_bat(w):
        return
    _expire(w)
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid):
            continue
        for quote_id in sorted(str(x) for x in getattr(ke_hoach[aid], "huy_bao_gia", ())):
            _cancel(w, aid, quote_id)
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid):
            continue
        for raw in getattr(ke_hoach[aid], "dang_bao_gia", ()):
            _post(w, aid, raw)
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid):
            continue
        for raw in getattr(ke_hoach[aid], "chap_nhan_bao_gia", ()):
            _accept(w, aid, raw)


def giao_hang_den_han(w: Any) -> None:
    """Settle only pending forward fills whose pre-declared delivery tick has arrived."""
    if not _bao_gia_bat(w):
        return
    for _qid, q in sorted(w.bao_gia.items()):
        for fill in q.fills:
            if fill.status == "pending" and fill.due_tick <= w.tick:
                _settle_fill(w, q, fill)
        _cap_nhat_trang_thai(w, q)


def dong_bo_ky_quy(w: Any) -> None:
    """Reconcile the DECLARED escrow books to the ledger after physical decay.

    ``consumption.hao_hut_kho`` spoils stored food in EVERY ledger subject — agents,
    ``CONG_QUY``, and escrow holders alike. That is the model's existing physics: grain in a
    granary rots no matter whose name is on it. Escrow is not exempt, and exempting it would
    hand agents a free store of value (park grain in a quote nobody accepts, dodge the
    per-tick loss, cancel later) — an exploit that would itself confound the questions this
    model asks.

    So the ledger is the truth and the books must follow it. Without this, a quote escrowing
    24.0 kg reads ``sổ=23.5176 khai=24.0`` one tick later and ``kiem_tra_ky_quy`` fails the
    world audit. Delivery shortfall is already a modelled outcome: ``_settle_fill`` re-reads
    the actual balance and emits ``escrow_failed`` when it cannot cover the fill.
    """
    if not _bao_gia_bat(w):
        return
    for qid, q in sorted(w.bao_gia.items()):
        main = _holder(qid)
        for asset in sorted(q.escrow):
            thuc = w.ledger.so_du(main, asset)
            q.escrow[asset] = thuc if thuc > EPSILON else 0.0
        for asset in [a for a, v in q.escrow.items() if v <= EPSILON]:
            q.escrow.pop(asset, None)
        for fill in q.fills:
            thuc = w.ledger.so_du(fill.counterparty_holder, fill.counterparty_asset)
            fill.counterparty_amount = thuc if thuc > EPSILON else 0.0


def kiem_tra_ky_quy(w: Any) -> list[str]:
    """Return audit failures for escrow declaration ↔ ledger balances; gate off is inert."""
    if not _bao_gia_bat(w):
        return []
    loi: list[str] = []
    for qid, q in sorted(w.bao_gia.items()):
        main = _holder(qid)
        for asset, declared in sorted(q.escrow.items()):
            actual = w.ledger.so_du(main, asset)
            if abs(actual - declared) > 1e-7:
                loi.append(f"ký quỹ {qid}/{asset}: sổ={actual} khai={declared}")
        for fill in q.fills:
            actual = w.ledger.so_du(fill.counterparty_holder, fill.counterparty_asset)
            if abs(actual - fill.counterparty_amount) > 1e-7:
                loi.append(
                    f"ký quỹ đối tác {qid}/{fill.counterparty_holder}/{fill.counterparty_asset}: "
                    f"sổ={actual} khai={fill.counterparty_amount}"
                )
        if q.trang_thai in {"hoan_thanh", "het_han", "da_huy"}:
            if q.con_lai > EPSILON:
                loi.append(f"báo giá đóng {qid} còn lượng treo {q.con_lai}")
    return loi


def metrics(w: Any) -> dict[str, Any] | None:
    """Observed quote-book and settlement coverage for P4 reporting."""
    if not _bao_gia_bat(w):
        return None
    book = list(getattr(w, "bao_gia", {}).values())
    fills = [fill for quote in book for fill in quote.fills]
    settled = sum(1 for fill in fills if fill.status == "settled")
    failed = sum(1 for fill in fills if fill.status == "failed")
    pending = sum(1 for fill in fills if fill.status == "pending")
    accepted = settled + failed + pending
    return {
        "n_bao_gia_mo": sum(1 for quote in book if quote.trang_thai == "dang_treo"),
        "do_sau_so_lenh": round(sum(max(0.0, quote.con_lai) for quote in book
                                   if quote.trang_thai == "dang_treo"), 9),
        "n_tai_san_co_bao_gia": len({quote.tai_san for quote in book}),
        "fills": {"pending": pending, "settled": settled, "failed": failed},
        "ty_le_chap_nhan_den_thanh_toan": (
            round(settled / accepted, 9) if accepted else None
        ),
    }


__all__ = [
    "BaoGia", "QuoteFill", "_bao_gia_bat", "buoc_bao_gia", "giao_hang_den_han",
    "kiem_tra_ky_quy", "metrics", "quote_visible_to", "xu_ly_nguoi_chet",
]
