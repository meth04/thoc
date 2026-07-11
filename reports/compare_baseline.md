# So sánh baseline: `mock300` (mode mock) vs `rb300` (mode rulebot)

- Seed: 42 / 42; tick cuối: 600 / 600
- Thời gian chạy: 243.7s / 287.8s
- `mock300`: 5875 call, fallback 0.00% (p_malformed=0.15)

| chỉ số | tick | mock300 | rb300 |
|---|---|---|---|
| dan_so | 100 | 85 | 159 |
| dan_so | 200 | 167 | 259 |
| dan_so | 300 | 264 | 368 |
| dan_so | 400 | 484 | 390 |
| dan_so | 500 | 565 | 405 |
| dan_so | 600 | 407 | 365 |
| thoc_moi_nguoi | 100 | 5223.2 | 5871.8 |
| thoc_moi_nguoi | 200 | 3032.1 | 3887.1 |
| thoc_moi_nguoi | 300 | 3704.8 | 3637.3 |
| thoc_moi_nguoi | 400 | 2975.9 | 3346.6 |
| thoc_moi_nguoi | 500 | 2131.8 | 2745.2 |
| thoc_moi_nguoi | 600 | 2934.7 | 3464.7 |
| gini_dat | 100 | 0.6312 | 0.7312 |
| gini_dat | 200 | 0.6923 | 0.7362 |
| gini_dat | 300 | 0.6342 | 0.7402 |
| gini_dat | 400 | 0.7305 | 0.7573 |
| gini_dat | 500 | 0.738 | 0.786 |
| gini_dat | 600 | 0.6973 | 0.7222 |
| gini_thoc | 100 | 0.6144 | 0.7592 |
| gini_thoc | 200 | 0.6485 | 0.7697 |
| gini_thoc | 300 | 0.6291 | 0.7535 |
| gini_thoc | 400 | 0.7032 | 0.7404 |
| gini_thoc | 500 | 0.7516 | 0.7826 |
| gini_thoc | 600 | 0.6966 | 0.7337 |
| ty_le_biet_chu | 100 | 0.6279 | 0.7857 |
| ty_le_biet_chu | 200 | 0.8289 | 1.0 |
| ty_le_biet_chu | 300 | 0.9504 | 0.9888 |
| ty_le_biet_chu | 400 | 0.9676 | 0.9845 |
| ty_le_biet_chu | 500 | 0.9836 | 0.9797 |
| ty_le_biet_chu | 600 | 1.0 | 0.983 |
| hd_hieu_luc | 100 | 73 | 149 |
| hd_hieu_luc | 200 | 102 | 219 |
| hd_hieu_luc | 300 | 87 | 379 |
| hd_hieu_luc | 400 | 124 | 468 |
| hd_hieu_luc | 500 | 190 | 599 |
| hd_hieu_luc | 600 | 236 | 645 |
| so_mo_tip | 100 | 4 | 6 |
| so_mo_tip | 200 | 6 | 4 |
| so_mo_tip | 300 | 5 | 5 |
| so_mo_tip | 400 | 5 | 5 |
| so_mo_tip | 500 | 8 | 4 |
| so_mo_tip | 600 | 5 | 5 |
| kl_giao_dich | 100 | 440.0 | 820.277 |
| kl_giao_dich | 200 | 972.0 | 880.002 |
| kl_giao_dich | 300 | 1034.009 | 2055.0 |
| kl_giao_dich | 400 | 1937.0 | 2020.0 |
| kl_giao_dich | 500 | 9467.97 | 2400.0 |
| kl_giao_dich | 600 | 2475.8 | 2780.8 |
| vo_gia_cu | 100 | 5 | 10 |
| vo_gia_cu | 200 | 7 | 14 |
| vo_gia_cu | 300 | 13 | 19 |
| vo_gia_cu | 400 | 14 | 16 |
| vo_gia_cu | 500 | 33 | 26 |
| vo_gia_cu | 600 | 10 | 11 |