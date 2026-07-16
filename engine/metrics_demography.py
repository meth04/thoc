"""Versioned, read-only demographic metrics.

The engine records a small per-tick exposure snapshot while it is executing.  The
snapshot is deliberately separate from the event journal: a resumed/concatenated
journal must never change a birth or mortality rate.  Nothing in this module is
consulted by production, consumption, or agent choice, so the state is outside
``World.behavioral_state`` and cannot change a replay hash.

The feature is enabled only by ``quan_sat.nhan_khau.bat`` in a versioned scenario.
It therefore leaves legacy metrics and legacy world hashes untouched.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import median
from typing import Any


def _bat(w: Any) -> bool:
    return bool(w.cfg.get("quan_sat.nhan_khau.bat", False))


def _cfg(w: Any) -> dict[str, Any]:
    raw = w.cfg.get("quan_sat.nhan_khau", {})
    if not isinstance(raw, dict):
        raise ValueError("quan_sat.nhan_khau phải là object")
    return raw


def _bands(w: Any) -> list[tuple[str, float, float | None]]:
    """Read and validate the disclosed age-band convention.

    Intervals are lower-inclusive and upper-exclusive.  Exactly one final open
    interval is allowed; it is needed for a conventional period life table.
    """
    rows = _cfg(w).get("bang_song", {}).get("bands", [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("quan_sat.nhan_khau.bang_song.bands phải là list không rỗng")
    out: list[tuple[str, float, float | None]] = []
    last_upper = -math.inf
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("mỗi age band phải là object")
        lower = float(row["tu"])
        upper_raw = row.get("den")
        upper = None if upper_raw is None else float(upper_raw)
        if not math.isfinite(lower) or lower < 0 or lower < last_upper:
            raise ValueError("age bands phải tăng dần, không âm")
        if upper is not None and (not math.isfinite(upper) or upper <= lower):
            raise ValueError("cận trên age band phải lớn hơn cận dưới")
        if upper is None and index != len(rows) - 1:
            raise ValueError("chỉ age band cuối cùng được mở")
        label = str(row.get("nhan") or (f"{lower:g}+" if upper is None
                                          else f"{lower:g}-{upper:g}"))
        if any(label == prior[0] for prior in out):
            raise ValueError("nhãn age band phải duy nhất")
        out.append((label, lower, upper))
        last_upper = math.inf if upper is None else upper
    return out


def _band_cua(w: Any, age: float) -> str | None:
    for label, lower, upper in _bands(w):
        if age >= lower and (upper is None or age < upper):
            return label
    return None


def _tick_record(w: Any) -> dict[str, Any]:
    record = getattr(w, "nhan_khau_tick", None)
    if not isinstance(record, dict) or record.get("tick") != w.tick:
        bat_dau_tick(w)
        record = w.nhan_khau_tick
    return record


def bat_dau_tick(w: Any) -> None:
    """Capture exposure before births/deaths in the current tick.

    A person alive at the beginning of a tick contributes one person-tick even if
    they die later in that tick.  A newborn begins exposure in the following tick.
    This makes denominators explicit and independent of the final population.
    """
    if not _bat(w):
        return
    ss = w.cfg.get("nhan_khau.sinh_san")
    lower_mother, upper_mother = (float(x) for x in ss["tuoi_me"])
    bands = {label: 0.0 for label, _lower, _upper in _bands(w)}
    alive = [a for a in w.agents.values() if a.con_song]
    for agent in alive:
        label = _band_cua(w, float(agent.tuoi_nam))
        if label is not None:
            bands[label] += 1.0
    w.nhan_khau_tick = {
        "tick": int(w.tick),
        "person_ticks": float(len(alive)),
        "woman_ticks": float(sum(
            1 for a in alive
            if a.gioi_tinh == "nu" and lower_mother <= a.tuoi_nam <= upper_mother
        )),
        "band_person_ticks": bands,
        "births": 0,
        "deliveries": 0,
        "twin_deliveries": 0,
        "deaths": [],
    }
    # Childbirth deaths are tagged by the demographic engine before ``cai_chet``
    # classifies the health state.  This is observation-only and never branches
    # behaviour.
    w.tu_vong_sinh_no_tick = set()


def ghi_sinh(w: Any) -> None:
    """Ghi một trẻ sinh sống; sinh đôi gọi hai lần trong cùng một ca sinh."""
    if _bat(w):
        _tick_record(w)["births"] += 1


def ghi_ca_sinh(w: Any, me_id: str, *, so_con: int) -> None:
    """Ghi một ca sinh và khoảng cách với ca trước của cùng mẹ.

    Đây là observation state do metrics sở hữu, không được engine đọc để quyết định.
    Sinh đôi là một ca sinh có hai trẻ, nên không tạo khoảng cách 0 giả.
    """
    if not _bat(w):
        return
    if so_con < 1:
        raise ValueError("so_con của một ca sinh phải >= 1")
    record = _tick_record(w)
    record["deliveries"] = int(record.get("deliveries", 0)) + 1
    if so_con > 1:
        record["twin_deliveries"] = int(record.get("twin_deliveries", 0)) + 1

    tracker = getattr(w, "nhan_khau_khoang_sinh", None)
    if not isinstance(tracker, dict):
        tracker = {"tick_sinh_truoc": {}, "khoang": []}
        w.nhan_khau_khoang_sinh = tracker
    previous_by_mother = tracker.setdefault("tick_sinh_truoc", {})
    intervals = tracker.setdefault("khoang", [])
    previous = previous_by_mother.get(str(me_id))
    if previous is not None:
        spacing = int(w.tick) - int(previous)
        if spacing <= 0:
            raise ValueError("hai ca sinh khác nhau của cùng mẹ phải ở tick tăng dần")
        intervals.append({
            "me": str(me_id),
            "tu_tick": int(previous),
            "den_tick": int(w.tick),
            "khoang_tick": spacing,
        })
    previous_by_mother[str(me_id)] = int(w.tick)


def danh_dau_tu_vong_sinh_no(w: Any, aid: str) -> None:
    if _bat(w):
        _tick_record(w)
        w.tu_vong_sinh_no_tick.add(aid)


def la_tu_vong_sinh_no(w: Any, aid: str) -> bool:
    return _bat(w) and aid in getattr(w, "tu_vong_sinh_no_tick", set())


def ghi_chet(w: Any, age: float, reason: str) -> None:
    if not _bat(w):
        return
    _tick_record(w)["deaths"].append({"tuoi": float(age), "ly_do": str(reason)})


def _copy_record(record: dict[str, Any]) -> dict[str, Any]:
    """Make checkpoint-safe primitive observation data, not an alias to live state."""
    return {
        "tick": int(record["tick"]),
        "person_ticks": float(record["person_ticks"]),
        "woman_ticks": float(record["woman_ticks"]),
        "band_person_ticks": {
            str(k): float(v) for k, v in sorted(record["band_person_ticks"].items())
        },
        "births": int(record["births"]),
        "deliveries": int(record.get("deliveries", record["births"])),
        "twin_deliveries": int(record.get("twin_deliveries", 0)),
        "deaths": [
            {"tuoi": float(d["tuoi"]), "ly_do": str(d["ly_do"])}
            for d in record["deaths"]
        ],
    }


def chot_tick(w: Any) -> None:
    """Append exactly one state-derived demographic observation for this tick."""
    if not _bat(w):
        return
    record = _tick_record(w)
    history = getattr(w, "nhan_khau_lich_su", None)
    if not isinstance(history, list):
        history = []
        w.nhan_khau_lich_su = history
    copied = _copy_record(record)
    if history and int(history[-1].get("tick", -1)) == w.tick:
        history[-1] = copied
    else:
        history.append(copied)
    window = int(_cfg(w)["cua_so_tick"])
    if window < 1:
        raise ValueError("quan_sat.nhan_khau.cua_so_tick phải >= 1")
    del history[:-window]


def _window(w: Any) -> list[dict[str, Any]]:
    chot_tick(w)
    return list(getattr(w, "nhan_khau_lich_su", []))


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(float(value), 9)


def _rate(count: int, exposure: float, ticks_per_year: int, minimum: float) -> float | None:
    if exposure < minimum:
        return None
    return count / exposure * ticks_per_year


def _life_table(w: Any, history: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = _cfg(w)["bang_song"]
    minimum = float(cfg["min_person_tick_moi_band"])
    if minimum <= 0:
        raise ValueError("min_person_tick_moi_band phải dương")
    bands = _bands(w)
    exposure: dict[str, float] = defaultdict(float)
    deaths: Counter[str] = Counter()
    for record in history:
        for label, value in record["band_person_ticks"].items():
            exposure[str(label)] += float(value)
        for death in record["deaths"]:
            label = _band_cua(w, float(death["tuoi"]))
            if label is not None:
                deaths[label] += 1

    ticks_per_year = w.tick_moi_nam()
    rows: list[dict[str, Any]] = []
    complete = True
    hazards: list[tuple[float, float | None, float]] = []
    for label, lower, upper in bands:
        person_ticks = exposure[label]
        death_count = int(deaths[label])
        if person_ticks < minimum:
            rows.append({
                "nhan": label,
                "tu": lower,
                "den": upper,
                "exposure_person_tick": _round_or_none(person_ticks),
                "n_chet": death_count,
                "nqx": None,
            })
            complete = False
            continue
        exposure_years = person_ticks / ticks_per_year
        hazard = death_count / exposure_years if exposure_years > 0 else math.nan
        if not math.isfinite(hazard):
            complete = False
        if upper is None:
            # The open interval needs an observed positive hazard.  A zero death
            # count would imply an infinite tail, so e0 is honestly undefined.
            nqx = 1.0 if hazard > 0 else None
            if hazard <= 0:
                complete = False
        else:
            nqx = 1.0 - math.exp(-hazard * (upper - lower)) if hazard >= 0 else None
        rows.append({
            "nhan": label,
            "tu": lower,
            "den": upper,
            "exposure_person_tick": _round_or_none(person_ticks),
            "n_chet": death_count,
            "nqx": _round_or_none(nqx),
        })
        hazards.append((lower, upper, hazard))

    e0: float | None = None
    if complete and len(hazards) == len(bands):
        survivors = 100_000.0
        person_years = 0.0
        for lower, upper, hazard in hazards:
            if upper is None:
                if hazard <= 0:
                    e0 = None
                    break
                person_years += survivors / hazard
                survivors = 0.0
                continue
            width = upper - lower
            if hazard <= 0:
                person_years += survivors * width
            else:
                after = survivors * math.exp(-hazard * width)
                person_years += (survivors - after) / hazard
                survivors = after
        else:
            e0 = person_years / 100_000.0
    return {
        "method": "constant_hazard_period_life_table",
        "exposure_person_tick": _round_or_none(sum(exposure.values())),
        "bands": rows,
        "e0_period": _round_or_none(e0),
    }


def _birth_spacing(w: Any) -> dict[str, Any]:
    """Khoảng cách giữa các CA SINH, không phải giữa từng trẻ trong ca sinh đôi."""
    tracker = getattr(w, "nhan_khau_khoang_sinh", None)
    rows = tracker.get("khoang", []) if isinstance(tracker, dict) else []
    values = [
        int(row["khoang_tick"])
        for row in rows
        if isinstance(row, dict) and int(row.get("khoang_tick", 0)) > 0
    ]
    if not values:
        return {
            "pham_vi": "toan_run_tu_khi_bat_metric",
            "n_khoang": 0,
            "min_tick": None,
            "trung_binh_tick": None,
            "trung_vi_tick": None,
            "min_nam": None,
            "trung_binh_nam": None,
            "trung_vi_nam": None,
        }
    ticks_per_year = float(w.tick_moi_nam())
    mean_tick = sum(values) / len(values)
    median_tick = float(median(values))
    return {
        "pham_vi": "toan_run_tu_khi_bat_metric",
        "n_khoang": len(values),
        "min_tick": min(values),
        "trung_binh_tick": _round_or_none(mean_tick),
        "trung_vi_tick": _round_or_none(median_tick),
        "min_nam": _round_or_none(min(values) / ticks_per_year),
        "trung_binh_nam": _round_or_none(mean_tick / ticks_per_year),
        "trung_vi_nam": _round_or_none(median_tick / ticks_per_year),
    }


def _reproduction(w: Any, history: list[dict[str, Any]]) -> dict[str, Any] | None:
    ss = w.cfg.get("nhan_khau.sinh_san")
    if not isinstance(ss, dict) or "thai_ky_tick" not in ss:
        return None
    current = history[-1] if history else {}
    births = sum(int(record.get("births", 0)) for record in history)
    deliveries = sum(int(record.get("deliveries", record.get("births", 0)))
                     for record in history)
    twins = sum(int(record.get("twin_deliveries", 0)) for record in history)
    return {
        "tre_sinh_song_tick": int(current.get("births", 0)),
        "ca_sinh_tick": int(current.get("deliveries", current.get("births", 0))),
        "ca_sinh_doi_tick": int(current.get("twin_deliveries", 0)),
        "tre_sinh_song_cua_so": births,
        "ca_sinh_cua_so": deliveries,
        "ca_sinh_doi_cua_so": twins,
        "dang_mang_thai": len(getattr(w, "thai_ky", {})),
        "dang_hau_san": len(getattr(w, "hau_san", {})),
        "khoang_cach_ca_sinh": _birth_spacing(w),
    }


def _residence(w: Any) -> dict[str, Any] | None:
    from engine.economy import household_snapshot
    from engine.household import _cu_tru_bat

    if not _cu_tru_bat(w):
        return None
    rows = household_snapshot(w)
    sizes = Counter(int(row["members"]) for row in rows)
    poor = sum(1 for row in rows if float(row["food_security"]) < 1.0)
    return {
        "n": len(rows),
        "co_so_thanh_vien": {str(k): v for k, v in sorted(sizes.items())},
        "ty_le_thieu_an": _round_or_none(poor / len(rows)) if rows else None,
        # This is keyed by stable residence id when the household gate is on.
        "thoi_gian_ngheo": {
            str(k): int(v) for k, v in sorted(getattr(w, "poverty_streak", {}).items())
        },
    }


def _estate(w: Any) -> dict[str, Any] | None:
    from engine.entities import tai_san_quy_thoc
    from engine.estate import _di_san_bat
    from engine.world import VO_THUA_NHAN

    if not _di_san_bat(w):
        return None
    open_estates = getattr(w, "di_san", {})
    return {
        "n_mo": len(open_estates),
        "n_dong": len(getattr(w, "di_san_xong", {})),
        "gia_tri_dang_treo": _round_or_none(sum(
            tai_san_quy_thoc(w, estate_id) for estate_id in open_estates
        )),
        "ket_vinh_vien": _round_or_none(tai_san_quy_thoc(w, VO_THUA_NHAN)),
    }


def tinh(w: Any) -> dict[str, Any] | None:
    """Return the P4 demographic surface, or ``None`` while the gate is off."""
    if not _bat(w):
        return None
    history = _window(w)
    cfg = _cfg(w)
    minimum_exposure = float(cfg["min_person_tick"])
    minimum_deaths = int(cfg["min_n_tu_vong"])
    minimum_women = float(cfg["min_woman_tick"])
    if minimum_exposure <= 0 or minimum_women <= 0 or minimum_deaths < 1:
        raise ValueError("ngưỡng quan_sat.nhan_khau không hợp lệ")

    living = [a for a in w.agents.values() if a.con_song]
    ages = [float(a.tuoi_nam) for a in living]
    current = history[-1] if history else {
        "births": 0, "deliveries": 0, "twin_deliveries": 0,
        "deaths": [], "person_ticks": 0.0, "woman_ticks": 0.0,
    }
    deaths = [death for record in history for death in record["deaths"]]
    ages_at_death = [float(death["tuoi"]) for death in deaths]
    current_causes = Counter(str(death["ly_do"]) for death in current["deaths"])
    exposure = sum(float(record["person_ticks"]) for record in history)
    woman_exposure = sum(float(record["woman_ticks"]) for record in history)
    births = sum(int(record["births"]) for record in history)
    ticks_per_year = w.tick_moi_nam()

    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    retirement_age = float(cfg["tuoi_nghi"])
    workers = sum(1 for age in ages if adult_age <= age <= retirement_age)
    dependents = sum(1 for age in ages if age < adult_age or age > retirement_age)
    dependency = dependents / workers if workers else None

    result: dict[str, Any] = {
        "cua_so_tick": int(cfg["cua_so_tick"]),
        "song": {
            "n": len(living),
            "tuoi_tb": _round_or_none(sum(ages) / len(ages)) if ages else None,
            "tuoi_trung_vi": _round_or_none(float(median(ages))) if ages else None,
        },
        "chet": {
            "n_tick": len(current["deaths"]),
            "theo_nguyen_nhan": dict(sorted(current_causes.items())),
            "n_cua_so": len(deaths),
            "tuoi_tb_khi_chet": _round_or_none(sum(ages_at_death) / len(ages_at_death))
            if len(ages_at_death) >= minimum_deaths else None,
            "tuoi_trung_vi_khi_chet": _round_or_none(float(median(ages_at_death)))
            if len(ages_at_death) >= minimum_deaths else None,
        },
        "exposure_person_tick": _round_or_none(exposure),
        "ty_suat_chet_moi_nguoi_moi_nam": _round_or_none(
            _rate(len(deaths), exposure, ticks_per_year, minimum_exposure)
        ),
        "ty_suat_sinh_moi_nguoi_moi_nam": _round_or_none(
            _rate(births, exposure, ticks_per_year, minimum_exposure)
        ),
        "ty_suat_sinh_theo_tuoi_me_moi_nam": _round_or_none(
            _rate(births, woman_exposure, ticks_per_year, minimum_women)
        ),
        "ty_le_phu_thuoc": _round_or_none(dependency),
        "sinh_san": _reproduction(w, history),
        "bang_song": _life_table(w, history),
        "cu_tru": _residence(w),
        "di_san": _estate(w),
    }
    # INV-M1: never add ``life_expectancy`` / ``tuoi_tho`` here.  e0_period above
    # is explicitly a period-life-table output with disclosed exposure and method.
    return result


__all__ = [
    "bat_dau_tick", "chot_tick", "danh_dau_tu_vong_sinh_no", "ghi_ca_sinh",
    "ghi_chet", "ghi_sinh", "la_tu_vong_sinh_no", "tinh",
]
