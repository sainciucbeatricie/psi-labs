# Laboratorul 3: Desenează limitele Dashboard-ului

## Domeniu și ținte de încărcare

Dashboard-ul permite unui Utilizator autentificat să răsfoiască și să filtreze Acțiuni, să citească prețuri și istoric și să administreze un Watchlist privat. Un Furnizor de date de piață oferă date întârziate și poate returna date invalide, limitări de rată (rate limit) sau căderi (outage).

Ținte de încărcare din Lab 2 (folosite la dimensionarea designului):

| Țintă | Valoare din Lab 2 |
|---|---|
| Utilizatori (trei scări) | 300 / 3.000 / 30.000 |
| Încărcare constantă de citiri | 79,2 / 792 / 7.920 RPS |
| Vârf la deschiderea pieței (cu marjă de 10%) | 103 / 1.030 / 10.296 RPS |
| Cea mai frecventă citire (Stock price) | 60 / 600 / 6.000 RPS |
| Latență | p95 al citirilor sub 2 s. O citire peste 2 s este întreruptă și returnează un rezultat marcat clar „indisponibil". |
| Disponibilitate | 99,9% în orele de piață (09:30-16:00, L-V), 99,5% în restul zilei |
| Prospețimea prețului | Până la 15 min: normal. Peste 15 min: marcat „întârziat". Peste 60 min fără actualizare: „indisponibil" (niciodată 0). |
| Consistența Watchlist-ului | Read-your-writes: următoarea citire a aceluiași Utilizator arată imediat modificarea |
| Stocare | Aproximativ 5.700 de Acțiuni, circa 71,1 MB/zi de istoric, circa 17,93 GB pe an (retenție 252 de zile) |

Consecințe ale acestor ținte asupra designului:
- Citirile Utilizatorilor sunt servite doar din Baza noastră de date, deci latența de citire nu depinde de Furnizor. Setul ultimelor prețuri este mic (circa 0,14 MB), deci cea mai frecventă citire (Stock price) poate fi servită rapid din Baza de date.
- Furnizorul este apelat doar de Colectorul de date de piață, după un program, deci numărul de Utilizatori nu schimbă numărul de cereri către Furnizor.
- Colectorul este un container separat, deci o problemă la Furnizor nu poate încetini sau întrerupe celelalte citiri.
- Citirile și scrierile Watchlist-ului folosesc aceeași Bază de date, iar succesul se raportează doar după commit, deci read-your-writes este respectat.

---

## 1. Diagrama de context al sistemului (System Context)

```mermaid
flowchart LR
    User["Utilizator<br/>(persoană autentificată)"]
    subgraph Boundary["Limita sistemului"]
        Dashboard["Dashboard<br/>Răsfoiește Acțiuni, citește prețuri și istoric, administrează Watchlist privat"]
    end
    Provider["Furnizor de date de piață<br/>(sistem extern, date întârziate)"]

    User -->|"Răsfoiește și filtrează Acțiuni, citește prețuri și istoric, administrează Watchlist (HTTPS)"| Dashboard
    Dashboard -->|"Cere date de piață întârziate (API HTTPS)"| Provider
    Provider -->|"Returnează date întârziate, sau date invalide, rate limit, cădere"| Dashboard
```

**Ipoteze**
- Autentificarea face parte din Dashboard. Utilizatorul ajunge deja autentificat, deci nu este desenat un sistem de identitate separat.
- Există un singur sistem extern: Furnizorul de date de piață.
- Pe acest nivel nu sunt arătate părți interne de execuție.

---

## 2. Diagrama de containere (Container)

```mermaid
flowchart LR
    User["Utilizator<br/>(persoană autentificată)"]
    Provider["Furnizor de date de piață<br/>(sistem extern)"]

    subgraph Boundary["Limita sistemului Dashboard"]
        App["Aplicația Dashboard<br/>Servește interfața web și răspunde cererilor Utilizatorilor"]
        Collector["Colector de date de piață<br/>Preia, validează și stochează datele Furnizorului"]
        DB[("Baza de date<br/>Stochează Acțiuni, prețuri, istoric, Watchlist-uri")]
    end

    User -->|"Răsfoiește, filtrează, citește prețuri, administrează Watchlist (HTTPS)"| App
    App -->|"Citește Acțiuni, prețuri, istoric și citește sau scrie Watchlist-uri (SQL)"| DB
    Collector -->|"Scrie prețuri și istoric validate (SQL)"| DB
    Collector -->|"Cere date întârziate cu credențiale păstrate pe server (HTTPS)"| Provider
```

**Responsabilități (câte una pentru fiecare parte)**
- **Aplicația Dashboard**: gestionează toate cererile Utilizatorilor (identitate, verificarea intrărilor, citiri, modificări de Watchlist).
- **Colector de date de piață**: rulează sincronizarea cu Furnizorul, validează datele și stochează doar datele acceptate.
- **Baza de date**: singurul loc de stocare pentru Acțiuni, prețuri, istoric și Watchlist-uri.

**Ipoteze**
- Acesta este cel mai mic set care îndeplinește cerințele: separarea Colectorului de Aplicație ține problemele Furnizorului departe de citirile Utilizatorilor, iar Baza de date este stocarea comună a celor două.
- Aplicația Dashboard nu apelează niciodată Furnizorul. Credențialele Furnizorului există doar în configurația Colectorului, pe server.
- Colectorul pornește sincronizările după propriul program.
- Nu se adaugă un container separat de cache. Datele ultimelor prețuri sunt mici și Baza de date le servește. Dacă testele de încărcare arată p95 peste 2 s, un cache este prima schimbare de luat în calcul.

---

## 3. Diagrama de componente (Aplicația Dashboard)

```mermaid
flowchart TB
    User["Utilizator<br/>(persoană)"]

    subgraph DA["Aplicația Dashboard (container)"]
        WI["Interfața web<br/>Primește cererile, validează intrările, afișează rezultatele"]
        AU["Autentificare<br/>Verifică identitatea Utilizatorului și sesiunea"]
        SB["Navigator de Acțiuni<br/>Răsfoiește și filtrează Acțiuni"]
        PR["Cititor de prețuri<br/>Citește prețuri și istoric, verifică vechimea datelor"]
        WM["Manager Watchlist<br/>Verifică permisiunile și modifică Watchlist-ul privat"]
        DAC["Acces la date<br/>Citește și scrie în Baza de date"]
    end

    DB[("Baza de date<br/>(container)")]

    User -->|"Cereri HTTPS"| WI
    WI -->|"Verifică sesiunea"| AU
    WI -->|"Cereri de răsfoire și filtrare"| SB
    WI -->|"Cereri de preț și istoric"| PR
    WI -->|"Cereri de modificare a Watchlist-ului"| WM
    SB -->|"Citește Acțiuni"| DAC
    PR -->|"Citește prețuri și istoric"| DAC
    WM -->|"Citește și scrie Watchlist"| DAC
    DAC -->|"Interogări și tranzacții SQL"| DB
```

**Ipoteze**
- Este deschisă doar Aplicația Dashboard. Utilizatorul și Baza de date sunt singurele elemente exterioare care comunică direct cu componentele ei.
- Colectorul de date de piață și Furnizorul nu apar, pentru că nu comunică direct cu Aplicația Dashboard. Colectorul ajunge la Aplicație doar prin datele stocate în Baza de date.
- Sesiunea este un token semnat, deci Autentificarea o poate verifica fără apel către stocare.

---

## 4. Diagrame de secvență

### A. Sincronizarea datelor de piață

```mermaid
sequenceDiagram
    participant C as Colector de date de piață
    participant P as Furnizor de date de piață
    participant D as Baza de date

    Note over C: Sincronizarea pornește după programul Colectorului
    C->>P: Cere prețuri întârziate (cheia API rămâne pe server)
    alt Timeout sau cădere a Furnizorului
        C->>C: Timeout sau 5xx, niciun răspuns utilizabil
        Note over C,D: Nu se scrie nimic. Datele acceptate anterior rămân neschimbate și pot fi citite.
        C->>C: Înregistrează eșecul și reîncearcă la următoarea sincronizare programată
    else Rate limit
        P-->>C: HTTP 429 Too Many Requests
        Note over C,D: Nu se scrie nimic. Datele acceptate anterior rămân neschimbate și pot fi citite.
        C->>C: Înregistrează eșecul și așteaptă înainte de următoarea sincronizare
    else Răspuns primit
        P-->>C: Lot de prețuri întârziate
        C->>C: Validează lotul (simboluri cunoscute, preț peste 0, timestamp valid, nu mai vechi decât cel anterior)
        alt Lot invalid
            Note over C,D: Lotul invalid este respins și nu este stocat niciodată. Datele acceptate anterior rămân neschimbate și pot fi citite.
            C->>C: Înregistrează respingerea
        else Lot valid
            C->>D: Stochează lotul într-o singură tranzacție (ultimele prețuri și puncte de istoric)
            alt Eșec de stocare
                D-->>C: Eroare de scriere
                C->>D: Rollback
                Note over C,D: Datele acceptate anterior rămân neschimbate și pot fi citite.
                C->>C: Înregistrează eșecul și reîncearcă la următoarea sincronizare programată
            else Stocat
                D-->>C: Commit reușit
                Note over C,D: Datele acceptate devin disponibile pentru citirile ulterioare doar după acest commit
            end
        end
    end
```

**Ipoteze**
- Sincronizarea este pornită de programul Colectorului, nu de o acțiune a Utilizatorului.
- Un lot este acceptat sau respins în întregime. O sincronizare eșuată sau respinsă nu schimbă niciodată datele acceptate anterior, iar Utilizatorii continuă să citească ultimele date acceptate.
- Cât timp sincronizările continuă să eșueze, prețurile păstrate îmbătrânesc: după 15 min citirile le arată ca „întârziate", după 60 min fără actualizare citirile arată „indisponibil" (niciodată 0).
- Credențialele Furnizorului rămân pe server (configurația Colectorului). Nu sunt trimise niciodată către browser.

### B. Citirea prețului unei Acțiuni

```mermaid
sequenceDiagram
    actor U as Utilizator
    participant W as Interfața web
    participant A as Autentificare
    participant R as Cititor de prețuri
    participant X as Acces la date
    participant D as Baza de date

    U->>W: Cere prețul unei Acțiuni după simbol
    W->>A: Verifică sesiunea
    alt Neautentificat
        A-->>W: Identitate respinsă
        W-->>U: 401 Autentificare necesară
    else Autentificat
        A-->>W: Identitatea Utilizatorului confirmată
        W->>W: Validează formatul simbolului
        alt Intrare invalidă
            W-->>U: 400 Simbol invalid
        else Intrare validă
            W->>R: Cere ultimul preț pentru simbol
            R->>X: Citește ultimul preț și ora
            X->>D: Interoghează prețul stocat
            alt Eșec de stocare sau niciun răspuns în 2 s
                D-->>X: Eroare sau niciun răspuns la timp
                X-->>R: Eroare de stocare
                R-->>W: Citire eșuată
                W-->>U: 503 Rezultat marcat „indisponibil"
            else Niciun preț stocat
                D-->>X: Niciun rând găsit
                X-->>R: Negăsit
                R-->>W: Preț lipsă
                W-->>U: 404 Preț indisponibil
            else Preț găsit
                D-->>X: Preț și ora actualizării
                X-->>R: Preț și ora actualizării
                R->>R: Verifică vechimea datelor față de limitele acceptate (15 min și 60 min)
                alt Vechime până la 15 min
                    R-->>W: Preț proaspăt
                    W-->>U: 200 Preț cu ora actualizării
                else Vechime peste 15 min și până la 60 min
                    R-->>W: Preț întârziat
                    W-->>U: 200 Ultimul preț cunoscut marcat „întârziat", cu ora actualizării
                else Vechime peste 60 min
                    R-->>W: Preț prea vechi
                    W-->>U: 200 Rezultat marcat „indisponibil", fără valoare de preț și niciodată 0
                end
            end
        end
    end
    Note over U,D: O citire a Utilizatorului nu apelează niciodată Furnizorul de date de piață. Citește doar date stocate.
```

**Ipoteze**
- Limitele de vechime acceptate vin din Lab 2: până la 15 min este normal, peste 15 min este marcat „întârziat", peste 60 min fără actualizare este „indisponibil" (niciodată 0).
- Dacă citirea nu se termină în 2 s (limita de latență din Lab 2), cererea este întreruptă, iar Utilizatorul primește un rezultat marcat clar „indisponibil", nu o cerere blocată.
- Un preț „întârziat" este afișat totuși, marcat clar și cu ora actualizării, ca Utilizatorul să nu fie indus în eroare.
- O citire a Utilizatorului nu necesită niciodată o cerere nouă către Furnizor. Doar Colectorul de date de piață comunică cu Furnizorul.

### C. Modificarea unui Watchlist privat

```mermaid
sequenceDiagram
    actor U as Utilizator
    participant W as Interfața web
    participant A as Autentificare
    participant M as Manager Watchlist
    participant X as Acces la date
    participant D as Baza de date

    U->>W: Cere adăugarea unei Acțiuni în Watchlist-ul meu
    W->>A: Verifică sesiunea
    alt Neautentificat
        A-->>W: Identitate respinsă
        W-->>U: 401 Autentificare necesară
    else Autentificat
        A-->>W: Identitatea Utilizatorului confirmată
        W->>W: Validează intrarea (formatul simbolului, Acțiunea există)
        alt Intrare invalidă
            W-->>U: 400 Intrare invalidă, Watchlist neschimbat
        else Intrare validă
            W->>M: Adaugă Acțiunea pentru Utilizatorul identificat
            M->>M: Verificare permisiuni (Watchlist-ul țintă trebuie să aparțină Utilizatorului identificat)
            alt Încercare neautorizată
                M-->>W: Permisiune refuzată
                W-->>U: 403 Interzis, Watchlist neschimbat
            else Permis
                M->>X: Salvează modificarea
                X->>D: Scrie într-o singură tranzacție
                alt Eșec de stocare
                    D-->>X: Eroare de scriere
                    X->>D: Rollback
                    X-->>M: Salvare eșuată
                    M-->>W: Modificare eșuată
                    W-->>U: 503 Nesalvat, Watchlist neschimbat
                else Salvat
                    D-->>X: Commit reușit
                    Note over X,D: Punctul de commit. Succesul poate fi raportat doar după acesta.
                    X-->>M: Salvat
                    M-->>W: Modificare efectuată
                    W-->>U: 200 Watchlist actualizat
                end
            end
        end
    end
    Note over U,D: Read-your-writes. Următoarea citire a aceluiași Utilizator: după succes, Watchlist-ul include noua Acțiune. După orice respingere sau eșec, arată Watchlist-ul anterior.
```

**Ipoteze**
- Proprietarul Watchlist-ului este luat din sesiunea verificată, niciodată din corpul cererii. Un Utilizator nu poate modifica Watchlist-ul altui Utilizator.
- Succesul este raportat doar după commit-ul în Baza de date. După o modificare respinsă sau eșuată, următoarea citire a aceluiași Utilizator arată exact Watchlist-ul de dinaintea cererii.
- Datele Watchlist-ului sunt private: sunt returnate doar proprietarului lor.

---

## Checklist

- [x] Am inclus o diagramă System Context, una Container și una Component.
- [x] Am inclus cele trei diagrame de secvență cerute.
- [x] Toate cele șase blocuri Mermaid se randează fără eroare.
- [x] Diagrama Component deschide doar Aplicația Dashboard.
- [x] Fluxurile mele arată rezultate normale, acțiuni respinse și rezultate de eșec.
- [x] Designul acoperă citiri normale, date private, preluarea datelor de la Furnizor și eșecurile.
