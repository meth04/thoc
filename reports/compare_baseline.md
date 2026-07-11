# So sánh baseline: `mock300` (mode mock) vs `rbv_42` (mode rulebot)

- Seed: 42 / 42; tick cuối: 600 / 600
- Thời gian chạy: 453.5s / 373.1s
- `mock300`: 5684 call, fallback 0.02% (p_malformed=0.15)

| chỉ số | tick | mock300 | rbv_42 |
|---|---|---|---|
| dan_so | 100 | 133 | 128 |
| dan_so | 200 | 241 | 219 |
| dan_so | 300 | 332 | 260 |
| dan_so | 400 | 356 | 260 |
| dan_so | 500 | 343 | 197 |
| dan_so | 600 | 355 | 188 |
| thoc_moi_nguoi | 100 | 5017.1 | 5731.0 |
| thoc_moi_nguoi | 200 | 3106.4 | 4171.4 |
| thoc_moi_nguoi | 300 | 3164.8 | 4310.9 |
| thoc_moi_nguoi | 400 | 2997.4 | 5549.6 |
| thoc_moi_nguoi | 500 | 2809.1 | 8099.7 |
| thoc_moi_nguoi | 600 | 2622.5 | 8012.2 |
| gini_dat | 100 | 0.6838 | 0.6446 |
| gini_dat | 200 | 0.7303 | 0.72 |
| gini_dat | 300 | 0.7633 | 0.6751 |
| gini_dat | 400 | 0.7707 | 0.7554 |
| gini_dat | 500 | 0.7796 | 0.7327 |
| gini_dat | 600 | 0.8166 | 0.7285 |
| gini_thoc | 100 | 0.6929 | 0.7047 |
| gini_thoc | 200 | 0.7596 | 0.7868 |
| gini_thoc | 300 | 0.7826 | 0.7535 |
| gini_thoc | 400 | 0.7958 | 0.8154 |
| gini_thoc | 500 | 0.7964 | 0.8046 |
| gini_thoc | 600 | 0.8067 | 0.785 |
| ty_le_biet_chu | 100 | 0.4848 | 0.7097 |
| ty_le_biet_chu | 200 | 0.8529 | 0.9663 |
| ty_le_biet_chu | 300 | 0.9879 | 1.0 |
| ty_le_biet_chu | 400 | 0.9576 | 0.9922 |
| ty_le_biet_chu | 500 | 1.0 | 0.9714 |
| ty_le_biet_chu | 600 | 1.0 | 0.99 |
| hd_hieu_luc | 100 | 204 | 108 |
| hd_hieu_luc | 200 | 280 | 122 |
| hd_hieu_luc | 300 | 470 | 145 |
| hd_hieu_luc | 400 | 497 | 147 |
| hd_hieu_luc | 500 | 502 | 128 |
| hd_hieu_luc | 600 | 452 | 154 |
| so_mo_tip | 100 | 6 | 5 |
| so_mo_tip | 200 | 7 | 6 |
| so_mo_tip | 300 | 6 | 6 |
| so_mo_tip | 400 | 8 | 6 |
| so_mo_tip | 500 | 7 | 7 |
| so_mo_tip | 600 | 6 | 5 |
| kl_giao_dich | 100 | 1177.7 | 3071.0 |
| kl_giao_dich | 200 | 2374.2 | 2732.0 |
| kl_giao_dich | 300 | 5950.4 | 2112.915 |
| kl_giao_dich | 400 | 7185.2 | 1717.0 |
| kl_giao_dich | 500 | 8313.0 | 1721.344 |
| kl_giao_dich | 600 | 10684.026 | 1633.5 |
| vo_gia_cu | 100 | 10 | 5 |
| vo_gia_cu | 200 | 15 | 13 |
| vo_gia_cu | 300 | 19 | 12 |
| vo_gia_cu | 400 | 15 | 11 |
| vo_gia_cu | 500 | 21 | 8 |
| vo_gia_cu | 600 | 13 | 5 |