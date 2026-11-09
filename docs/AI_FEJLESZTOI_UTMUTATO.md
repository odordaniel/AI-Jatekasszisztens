# AI Játékasszisztens v1.9 – fejlesztői átadás más AI számára

## Projekt és hatókör
Windows 11, PySide6 GUI, rendszerértesítési tálcaikon. Képernyőrészletet jelöl ki vagy FPS-ben a középső területet rögzíti, majd a JPEG képet OpenAI-kompatibilis multimodális Chat Completions API-ra küldi magyar fordításért. Ez a csomag **csak dokumentációt ad hozzá** a v1.9-hez; az alkalmazás forrása és buildje változatlan. A v1.8-at a felhasználó működőnek jelezte; v1.9 Windows alatt itt nincs tesztelve.

## Olvasási sorrend és fájlok
1. `AI_START_HERE.md` – belépési pont.
2. `docs/AI_FEJLESZTOI_UTMUTATO.md` – jelen részletes útmutató.
3. `README.md` – felhasználói útmutató.
4. `src/assistant.py` – teljes alkalmazáskód, ne cseréld le általános sablonnal.
5. `requirements.txt`, `build_portable.bat`, `build_portable.ps1` – build; `src/app.ico` – ikon.

## Kód térképe (src/assistant.py)
- `main()` – QApplication, egy példány (`QLockFile`), tálcaikon, parancsok és szálak életciklusa.
- `Overlay(QWidget)` – modern UI, beállítások, előzmények, mentett ablakgeometria és állapot.
- `RegionSelector(QWidget)` – interaktív területkijelölés és megszakítás.
- `Translator(QThread)` – JPEG base64 kép + fordítási prompt, HTTP-kérés, elsődleges/fallback modell, hibaüzenet.
- `models_endpoint`, `fetch_available_models`, `ModelDiscovery(QThread)` – API-kapcsolat és modelllista.
- `HistoryStore` – előzmények, mappák, átnevezés, áthelyezés, törlés, JSON mentés.
- `ShortcutRecorder(QLineEdit)` – lenyomott billentyű/egérgomb rögzítése.
- `parse_hotkey`, `normalize_hotkeys`, `Hotkeys` – kombinációk, ütközések, globális Windows bemenet.
- `validate_api_url`, `tls_verify_for` – végpont- és HTTPS-ellenőrzés.
- `load_config`, `write_config`, `save_api_key`, `read_api_key` – beállítások, Credential Manager.
- `migrate_previous_install` – régi adatfájlok átvétele.
- `startup_registered`, `set_startup` – Windows bejelentkezéskori automatikus indítás.

## Funkcionális szerződés – regressziót ne okozz
- Induláskor csak tálcaikon, **nincs konzol vagy automatikus felugró ablak**.
- Jobb kattintásos tálcamenü: területkijelölés, FPS-középső kivágás, előzmények, beállítások, autostart, teljes kilépés.
- Területkijelölés és FPS-fordítás után **csak a fordítás** jelenik meg, előzmények nem.
- A legutóbbi **kézi** előzmény-nyitott/csukott állapot megmarad újranyitáskor. Automatikus fordítás miatti összecsukás ezt nem írhatja felül.
- A fordítási, előzményes és beállításnézet külön méretet tárol; az ablak pozíciója is mentett.
- A „kilépés” gyorsbillentyű a látható ablakot rejti el, kijelölés közben megszakít, **nem zárja be** a tálcán futó programot. Teljes kilépés a tálcamenüből.
- Gyorsbillentyűk szabadon rögzíthetők, Mouse3 (görgő), Mouse4, Mouse5 támogatott; játékbeli gombnyomást a hook nem nyeli el.
- Előzmények kereshetők, átnevezhetők, mappákba rendezhetők, törölhetők; törlési megerősítés ugyanabban az ablakban.
- API URL, kulcs, elsődleges/fallback modell és modelllista lekérés a beállításokban.
- Az API **képet** kap, nem pusztán felismert szöveget; nincs folyamatos képernyőmentés.

## Adatok és biztonság
Felhasználói adatok: `%LOCALAPPDATA%\AIJatekasszisztens`:
- `config.json` – URL, modell, gyorsbillentyűk; API-kulcsot **nem** szabad plaintext tárolni.
- `forditasok.json` – fordítások; `forditas_mappak.json` – mappák.
- `ablak_beallitasok.json` – nézet- és ablakállapot.
- `caddy-root.crt` – opcionális Caddy belső CA, csak `.home.arpa` HTTPS-hez.
- `hiba.log` – hibák, titkok nélkül; `application.lock` – egyetlen példány.
API-kulcs: Windows Credential Manager, `keyring`, szolgáltatás `AIJatekasszisztens`, bejegyzés `translation-api-key`.
Távoli API-hoz HTTPS kötelező, HTTP csak localhost. Nyilvános API-hoz normál CA; a belső Caddy CA-t ne alkalmazd globálisan. Az API átirányítás, válaszméret és JPEG méretkorlát védelme maradjon meg. Ne naplózz képernyőképet, API-kulcsot vagy teljes bizalmas API-választ. Régi JSON-mentésekben migrálás után is lehetnek régi kulcsok.

## Folyamatábra szavakban
Terület: `Hotkeys` / tálcamenü → `translate()` → `RegionSelector` → `send_selection()` → JPEG → `Translator` háttérszál → API → `HistoryStore.add()` → `Overlay`.
FPS: `translate_center()` → panel elrejtése → `mss.MSS()` elsődleges monitor → középső százalékos kivágás → `send_selection()`.
Kijelölés megszakításakor nincs API-kérés. Képernyőkép csak kérésre készül. 429 kvótakorlát és 503 átmeneti szolgáltatáshiba lehetséges; automatikus retry-t csak külön felhasználói kérésre adj hozzá.

## Build
Windows, rövid könyvtárútvonal ajánlott (`C:\AIJA`), mert a PySide6 telepítés hosszú útvonalon hibázhat. `build_portable.bat` → PowerShell script → `.buildvenv` → pip → `py_compile` → PyInstaller `--windowed --onedir`. Kimenet: `dist\AIJatekasszisztens\AIJatekasszisztens.exe`; **a teljes mappát** másolni kell. Nincs Inno Setup telepítő. Az aláíratlan EXE-t a Windows Smart App Control blokkolhatja; nem szabad a védelem kikapcsolását vagy megkerülését a build részeként javasolni.

## Tesztelési lista
- Python `py_compile` és független, izolált logikai tesztek.
- Windows alatt tálcás indulás, dupla példány tiltása, autostart, kilépés.
- Területkijelölés és Esc/bezárás, FPS crop, Mouse3/4/5 és egyéni billentyűk.
- Előzmény-állapot kézi megjegyzése, fordítás utáni kompakt mód, ablakméretek és pozíció újraindítás után.
- Mentések/mappák átnevezése és törlése, migráció adatvesztés nélkül.
- API teszt sikeres képes fordítással, hibás kulccsal, 429/503-mal, fallback-kel, modelllistával, Caddy CA-val.
- Ne állíts Windowsos működést igazoltnak pusztán szintaktikai teszt alapján.

## Ismert korlátok
FPS/anti-cheat játékok blokkolhatják a globális hookokat vagy képernyőrögzítést. A fallback modell jelenleg ugyanazt az API URL-t és kulcsot használja. A modelllista nem garantál képfeldolgozási képességet. A „portable” EXE nem jelenti a profil hordozhatóságát: az adatok AppDatában vannak. A v1.8 állapotmentési viselkedése kifejezetten fontos regressziós eset.

## Átadási szabály más AI-nak
Mindig a v1.9 `src/assistant.py` konkrét függvényeiből indulj ki, és ellenőrizd a felhasználó ténylegesen futó verzióját. Változtatás előtt készíts másolatot, és ne törölj felhasználói adatot. A működő UI, gyorsbillentyűk és előzményállapot megtartása elsődleges. A jelen dokumentáció hozzáadása **nem módosítja az alkalmazás kódját**.
