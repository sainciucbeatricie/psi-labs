# Lab 2: Cuantificarea citirilor din Dashboard

>**Notă:** acest laborator pornește de la o versiune revizuită a produsului, restrânsă doar la date de piață, fără componenta de portofoliu/brokeraj din Lab 1 individual.

## 1. Cerințe de calitate

**Latență:** p95 din citiri < 2 s, măsurat de la primirea cererii de backend până la trimiterea răspunsului, în perioade aglomerate. Peste 2 s → cererea e întreruptă și returnează un rezultat marcat clar „indisponibil", nu rămâne blocată.

**Disponibilitate:**
- Ore de piață: 09:30–16:00, L–V → țintă **99,9%**
- Restul zilei → țintă **99,5%**
- Motiv: în ore de piață indisponibilitatea afectează tranzacții reale; în afara lor prețurile sunt oricum statice.
- Buget indisponibilitate/30 zile: ore de piață ≈ **8,2 min**; restul zilei ≈ **175 min**.

**Consistență:**
- Preț: ≤15 min → normal; >15 min → etichetă „întârziat"; >60 min fără update → „indisponibil" (nu 0).
- Watchlist: următoarea citire a aceluiași Utilizator după o modificare trebuie să arate imediat schimbarea (read-your-writes).

---

## 2. RPS constant

`RPS = Utilizatori × cotă × acțiuni/User/s`

| Citire | 300 | 3.000 | 30.000 |
|---|---|---|---|
| Overview (70%, 1/30s) | 7 | 70 | 700 |
| Filter (50%, 3/min) | 7,5 | 75 | 750 |
| Stock price (20%, 1/s) | 60 | 600 | 6.000 |
| History (20%, 1/5min) | 0,2 | 2 | 20 |
| Watchlist (60%, 1/min) | 3 | 30 | 300 |
| Search (10%, 3/min) | 1,5 | 15 | 150 |
| **Total** | **79,2** | **792** | **7.920** |

---

## 3. RPS la deschiderea pieței

Suplimentar, într-o fereastră de 10 s: 30% fac 1 refresh Overview; 18% (60% din cei 30%) fac și 1 refresh Watchlist.

| | 300 | 3.000 | 30.000 |
|---|---|---|---|
| Trafic constant | 79,2 | 792 | 7.920 |
| + Overview (U×0,30/10s) | 9 | 90 | 900 |
| + Watchlist (U×0,18/10s) | 5,4 | 54 | 540 |
| Subtotal | 93,6 | 936 | 9.360 |
| +10% marjă | 102,96 | 1.029,6 | 10.296 |
| **Țintă finală (rotunjit)** | **103** | **1.030** | **10.296** |

---

## 4. Stocare

**Scop:** doar acțiuni ordinare (common stock), NYSE + NASDAQ, active, domestice+străine. Excluse: preferențiale, ADR, ETF, fonduri, delistate.
**Nr. acțiuni:** ≈ **5.700** (2.272 NYSE + 3.432 NASDAQ, sfârșit 2023, sursă: Statista/WFE). Definiție instrument: Investopedia „Common Stock".

**Date sincronizate:** date de referință (simbol, nume, bursă, sector) → Overview/Filter/Search; ultimul preț+oră → Overview/Watchlist/Stock price; istoric preț (1 min, doar ore de piață, 390 pct/zi, retenție 252 zile) → History. Alte date de la furnizor: niciuna necesară în v1.

| Set | Nr. înregistrări | B/înreg. | Stocare |
|---|---|---|---|
| Referință | 5.700 | ~150 B | 0,86 MB |
| Ultimele prețuri | 5.700 | ~24 B | 0,14 MB |
| Istoric (1 an) | 5.700×390×252=560.196.000 | ~32 B | 17,93 GB |
| **Total (1 an)** | **560.207.400** | — | **≈17,93 GB** |

- **Inițial** (fără istoric): ≈ 1 MB
- **Zilnic** (doar istoric): 5.700×390×32B ≈ **71,1 MB/zi**
- **1 an**: ≈ **17,93 GB** (plafon, retenție glisantă 252 zile)

---

## 5. Blocaje potențiale

| Calitate | Blocaj | Dovadă | Efect | De măsurat |
|---|---|---|---|---|
| Latență | Stock price (cea mai frecventă citire) | RPS cel mai mare la orice scară (6.000 la 30k) | Poate depăși 2s fără caching | p95/p99 doar pe acest endpoint |
| Consistență | Sincronizare Furnizor → „ultimul preț" | Provider deja 15 min întârziat | Etichetă „întârziat" poate rămâne în urmă | Întârziere ingestie sub sarcină |
| Throughput | Vârf Overview+Watchlist la deschidere, în 10s | Salt de la 7.920 la 10.296 RPS foarte rapid | Pool-uri saturate, timeout-uri | Rată cereri/erori în test simulat |
| Disponibilitate | Izolarea față de Furnizor | Regulile presupun deja nefiabilitate furnizor | Cădere furnizor poate trage după sine și alte citiri | Uptime celorlalte citiri în timpul unei căderi simulate |

---

## Checklist

- [x] Cerințe măsurabile pentru toate calitățile de bază
- [x] Ținte de uptime alese și justificate pentru ambele părți ale zilei
- [x] Calcule RPS constante și de deschidere de piață pentru toate cele trei scări
- [x] Scop de acțiuni susținute cercetat și definit
- [x] Stocare inițială, zilnică și pe un an estimate
- [x] Asumpții, unități, ferestre și rotunjire finală precizate
- [x] Un blocaj potențial analizat pentru fiecare calitate de bază
